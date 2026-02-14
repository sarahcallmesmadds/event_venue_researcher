"""Venue health check agent.

Verifies that venues in the Notion database are still active/in business
by searching the web for each one. Updates status and flags stale entries.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import anthropic

from event_research.config import Config
from event_research.notion_sync import get_all_venues, get_notion_client, archive_venue


@dataclass
class HealthCheckResult:
    """Result of checking a single venue."""

    page_id: str
    venue_name: str
    city: str
    status: str  # "active", "closed", "uncertain", "error"
    details: str  # explanation of finding
    updated_info: dict | None = None  # any corrected info (phone, website, etc.)


# Web search tool for health checks
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}

HEALTH_CHECK_SYSTEM = """\
You are a venue verification agent. Your job is to check if a venue is still \
open and active by searching the web. Be thorough but concise.
"""


def check_venue_health(
    venue_name: str,
    address: str,
    city: str,
    website: str | None,
    config: Config,
) -> dict:
    """Check if a single venue is still active using web search.

    Returns a dict with:
      - status: "active", "closed", or "uncertain"
      - details: explanation
      - updated_info: dict of any corrected/new info found
    """
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    prompt = (
        f"Check if this venue is still open and active:\n\n"
        f"Name: {venue_name}\n"
        f"Address: {address}\n"
        f"City: {city}\n"
    )
    if website:
        prompt += f"Website: {website}\n"

    prompt += (
        "\nSearch for this venue and determine:\n"
        "1. Is it still open/active? (check for permanent closure notices, "
        "Google Maps status, recent reviews, social media activity)\n"
        "2. Has any key info changed? (new phone, new website, new address)\n\n"
        "Return a JSON object:\n"
        "{\n"
        '  "status": "active" or "closed" or "uncertain",\n'
        '  "details": "Brief explanation of what you found",\n'
        '  "updated_info": {\n'
        '    "phone": "new phone if changed",\n'
        '    "website": "new website if changed",\n'
        '    "email": "new email if found"\n'
        "  }\n"
        "}\n\n"
        "Only include fields in updated_info if you found NEW or CORRECTED information. "
        "If nothing changed, set updated_info to null.\n"
        "Return ONLY the JSON object."
    )

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=2000,
            system=HEALTH_CHECK_SYSTEM,
            tools=[WEB_SEARCH_TOOL],
            messages=[{"role": "user", "content": prompt}],
        )

        # Handle agentic loop for web search
        messages = [{"role": "user", "content": prompt}]
        for _ in range(5):
            if response.stop_reason == "end_turn":
                break
            messages.append({"role": "assistant", "content": response.content})
            tool_results = [b for b in response.content if b.type == "web_search_tool_result"]
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
                response = client.messages.create(
                    model=config.model,
                    max_tokens=2000,
                    system=HEALTH_CHECK_SYSTEM,
                    tools=[WEB_SEARCH_TOOL],
                    messages=messages,
                )
            else:
                break

        # Extract text
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        # Strip citations
        text = re.sub(r'<cite[^>]*>(.*?)</cite>', r'\1', text, flags=re.DOTALL)

        # Parse JSON
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])

        return {"status": "uncertain", "details": f"Could not parse response: {text[:200]}"}

    except Exception as e:
        return {"status": "error", "details": f"Health check failed: {str(e)}"}


def _extract_property_text(page: dict, prop_name: str) -> str:
    """Extract text value from a Notion page property."""
    prop = page.get("properties", {}).get(prop_name, {})
    prop_type = prop.get("type", "")

    if prop_type == "title":
        items = prop.get("title", [])
        return items[0].get("plain_text", "") if items else ""
    elif prop_type == "rich_text":
        items = prop.get("rich_text", [])
        return items[0].get("plain_text", "") if items else ""
    elif prop_type == "select":
        sel = prop.get("select")
        return sel.get("name", "") if sel else ""
    elif prop_type == "url":
        return prop.get("url", "") or ""
    elif prop_type == "phone_number":
        return prop.get("phone_number", "") or ""
    elif prop_type == "email":
        return prop.get("email", "") or ""
    return ""


def run_health_checks(config: Config, limit: int = 0) -> list[HealthCheckResult]:
    """Run health checks on all non-archived venues in Notion.

    Args:
        config: App config
        limit: Max venues to check (0 = all)

    Returns:
        List of HealthCheckResult for each venue checked.
    """
    notion = get_notion_client(config)
    pages = get_all_venues(config)

    if limit > 0:
        pages = pages[:limit]

    results = []
    total = len(pages)

    print(f"\n🏥 Running health checks on {total} venue(s)...\n")

    for i, page in enumerate(pages, 1):
        name = _extract_property_text(page, "Name")
        address = _extract_property_text(page, "Address")
        city = _extract_property_text(page, "City")
        website = _extract_property_text(page, "Website")
        page_id = page["id"]

        print(f"  [{i}/{total}] Checking '{name}'...", end=" ", flush=True)

        check = check_venue_health(name, address, city, website, config)
        status = check.get("status", "uncertain")
        details = check.get("details", "")
        updated_info = check.get("updated_info")

        result = HealthCheckResult(
            page_id=page_id,
            venue_name=name,
            city=city,
            status=status,
            details=details,
            updated_info=updated_info,
        )
        results.append(result)

        # Take action based on status
        if status == "closed":
            print("❌ CLOSED — archiving")
            archive_venue(notion, page_id)
        elif status == "active":
            print("✅ Active")
            # Update any corrected info
            if updated_info:
                _update_venue_info(notion, page_id, updated_info)
        else:
            print(f"❓ {status}")

        # Rate limit courtesy — wait between checks
        if i < total:
            time.sleep(2)

    # Summary
    active = sum(1 for r in results if r.status == "active")
    closed = sum(1 for r in results if r.status == "closed")
    uncertain = sum(1 for r in results if r.status in ("uncertain", "error"))

    print(f"\n📊 Health Check Summary:")
    print(f"   ✅ Active: {active}")
    print(f"   ❌ Closed/Archived: {closed}")
    print(f"   ❓ Uncertain: {uncertain}")

    return results


def _update_venue_info(notion, page_id: str, updated_info: dict) -> None:
    """Update a venue's Notion page with corrected info from health check."""
    properties = {}

    if updated_info.get("phone"):
        properties["Phone"] = {"phone_number": updated_info["phone"]}
    if updated_info.get("website"):
        properties["Website"] = {"url": updated_info["website"]}
    if updated_info.get("email"):
        properties["Email"] = {"email": updated_info["email"]}

    if properties:
        try:
            notion.pages.update(page_id=page_id, properties=properties)
            print(f"      📝 Updated: {', '.join(properties.keys())}")
        except Exception as e:
            print(f"      ⚠️  Failed to update: {e}")
