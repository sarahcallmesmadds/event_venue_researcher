"""Outreach agent — contact enrichment + email drafting.

Uses Claude with web search to enrich venue contact data (find event
coordinators, direct emails, phone numbers, private events pages).
Then drafts personalized outreach emails using event details from
a linked Team Project page or manually provided brief.
"""

from __future__ import annotations

import json
import re
import time

import anthropic

from event_research.config import Config
from event_research.health_check import _extract_property_text
from event_research.models import EnrichedVenue, OutreachResult
from event_research.templates.outreach import (
    ENRICHMENT_SYSTEM_PROMPT,
    EMAIL_SYSTEM_PROMPT,
    EVENT_DETAILS_EXTRACT_PROMPT,
    build_enrichment_prompt,
    build_email_prompt,
)


# ---- Constants ----

WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 10,
}

MAX_ENRICHMENT_TURNS = 8
HAIKU_MODEL = "claude-haiku-4-20250414"


# ---- Retry helper (same pattern as agent.py) ----

def _call_with_retry(client, model, system, messages, tools=None, max_tokens=4000, max_retries=3):
    """Call the API with automatic retry on rate limit errors."""
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools

    for attempt in range(max_retries):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"   \u23f3 Rate limited \u2014 waiting {wait}s before retry ({attempt + 1}/{max_retries})...")
            time.sleep(wait)
    # Final attempt without catching
    return client.messages.create(**kwargs)


# ---- JSON extraction (same pattern as agent.py) ----

def _extract_json(text: str) -> dict | None:
    """Try multiple strategies to extract JSON from the response text."""
    # Strategy 1: Direct parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # Strategy 2: Remove markdown code fences
    cleaned = text.strip()
    if "```" in cleaned:
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        try:
            return json.loads("\n".join(lines))
        except json.JSONDecodeError:
            pass

    # Strategy 3: Find the outermost JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def _strip_citations(text: str) -> str:
    """Remove <cite index='...'>...</cite> tags, keeping the inner text."""
    return re.sub(r'<cite[^>]*>(.*?)</cite>', r'\1', text, flags=re.DOTALL)


# ---- Contact Enrichment ----

def enrich_venue_contact(
    venue_name: str,
    address: str,
    city: str,
    website: str | None,
    config: Config,
) -> dict:
    """Enrich contact data for a single venue using web search.

    Returns a dict with:
      - contact_name, contact_title, email, phone
      - private_events_url, booking_form_url
      - enrichment_notes, confidence
    """
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    prompt = build_enrichment_prompt(venue_name, address, city, website)

    messages = [{"role": "user", "content": prompt}]

    try:
        response = _call_with_retry(
            client, config.model, ENRICHMENT_SYSTEM_PROMPT,
            messages, tools=[WEB_SEARCH_TOOL], max_tokens=4000,
        )

        # Agentic loop for web search (same pattern as health_check.py)
        for _ in range(MAX_ENRICHMENT_TURNS):
            if response.stop_reason == "end_turn":
                break
            messages.append({"role": "assistant", "content": response.content})
            tool_results = [b for b in response.content if b.type == "web_search_tool_result"]
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
                response = _call_with_retry(
                    client, config.model, ENRICHMENT_SYSTEM_PROMPT,
                    messages, tools=[WEB_SEARCH_TOOL], max_tokens=4000,
                )
            else:
                break

        # Extract text
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        text = _strip_citations(text)
        data = _extract_json(text)

        if data:
            # Clean up any citation artifacts in values
            for key in data:
                if isinstance(data[key], str):
                    data[key] = _strip_citations(data[key])
            return data

        return {
            "enrichment_notes": f"Could not parse enrichment response: {text[:300]}",
            "confidence": "low",
        }

    except Exception as e:
        return {
            "enrichment_notes": f"Enrichment failed: {str(e)}",
            "confidence": "low",
        }


# ---- Event Details Extraction ----

def extract_event_details_from_page(page_content: str, config: Config) -> dict | None:
    """Extract event details from free-form Notion page content using Claude.

    Returns a dict with keys like event_type, date, guest_count, budget,
    vibe, audience, requirements. Returns None if extraction fails.
    """
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    prompt = EVENT_DETAILS_EXTRACT_PROMPT + page_content[:4000]  # Limit content length

    try:
        response = _call_with_retry(
            client, HAIKU_MODEL,
            "You extract structured data from text. Return only JSON.",
            [{"role": "user", "content": prompt}],
            max_tokens=1000,
        )

        text = response.content[0].text.strip()
        return _extract_json(text)

    except Exception as e:
        print(f"   \u26a0\ufe0f  Failed to extract event details: {e}")
        return None


# ---- Email Drafting ----

def draft_outreach_email(
    venue_name: str,
    contact_name: str | None,
    highlights: str | None,
    event_details: dict,
    private_events_url: str | None,
    config: Config,
) -> dict | None:
    """Draft a personalized outreach email for a venue.

    Returns a dict with 'subject' and 'body' keys, or None on failure.
    """
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    prompt = build_email_prompt(
        venue_name, contact_name, highlights, event_details, private_events_url,
    )

    try:
        response = _call_with_retry(
            client, HAIKU_MODEL, EMAIL_SYSTEM_PROMPT,
            [{"role": "user", "content": prompt}],
            max_tokens=2000,
        )

        text = response.content[0].text.strip()
        return _extract_json(text)

    except Exception as e:
        print(f"   \u26a0\ufe0f  Failed to draft email: {e}")
        return None


# ---- Full Pipeline ----

def run_outreach_for_venue(
    page: dict,
    config: Config,
    event_details: dict | None = None,
    enrich_only: bool = False,
    project_content: str | None = None,
) -> EnrichedVenue:
    """Run the full outreach pipeline for a single venue.

    1. Extract existing contact info from the Notion page
    2. Enrich contacts via web search
    3. If a linked project page is available, extract event details from it
    4. Draft outreach email (unless enrich_only)
    5. Return EnrichedVenue with all data

    Args:
        page: Notion page dict for the venue
        config: App config
        event_details: Pre-built event details dict (overrides project extraction)
        enrich_only: Skip email drafting if True
        project_content: Content from linked Team Project page (for detail extraction)
    """
    # Extract existing data from Notion page
    name = _extract_property_text(page, "Name")
    address = _extract_property_text(page, "Address")
    city = _extract_property_text(page, "City")
    website = _extract_property_text(page, "Website")
    phone = _extract_property_text(page, "Phone")
    email = _extract_property_text(page, "Email")
    contact_name = _extract_property_text(page, "Contact Name")
    highlights = _extract_property_text(page, "Highlights")
    price_range = _extract_property_text(page, "Price Range")
    neighborhood = _extract_property_text(page, "Neighborhood")
    page_id = page["id"]
    notion_url = page.get("url", "")

    result = EnrichedVenue(
        name=name,
        city=city,
        page_id=page_id,
        notion_url=notion_url,
        original_email=email or None,
        original_phone=phone or None,
        original_contact_name=contact_name or None,
        highlights=highlights or None,
        website=website or None,
        price_range=price_range or None,
        address=address or None,
        neighborhood=neighborhood or None,
    )

    # Step 1: Enrich contacts
    print(f"   \U0001f50d Enriching contacts...", end=" ", flush=True)
    enrichment = enrich_venue_contact(name, address, city, website, config)

    result.enriched_contact_name = enrichment.get("contact_name")
    result.enriched_contact_title = enrichment.get("contact_title")
    result.enriched_email = enrichment.get("email")
    result.enriched_phone = enrichment.get("phone")
    result.private_events_url = enrichment.get("private_events_url")
    result.booking_form_url = enrichment.get("booking_form_url")
    result.enrichment_confidence = enrichment.get("confidence", "medium")
    result.enrichment_notes = enrichment.get("enrichment_notes")

    # Count what's new
    new_info = []
    if result.enriched_email and result.enriched_email != result.original_email:
        new_info.append(f"email: {result.enriched_email}")
    if result.enriched_contact_name and result.enriched_contact_name != result.original_contact_name:
        new_info.append(f"contact: {result.enriched_contact_name}")
    if result.enriched_phone and result.enriched_phone != result.original_phone:
        new_info.append(f"phone: {result.enriched_phone}")
    if result.private_events_url:
        new_info.append("events page")

    if new_info:
        print(f"Found: {', '.join(new_info)}")
    else:
        print("No new info found")

    # Step 2: Extract event details from project content if needed
    if not event_details and project_content:
        print(f"   \U0001f4cb Extracting event details from project page...", end=" ", flush=True)
        event_details = extract_event_details_from_page(project_content, config)
        if event_details:
            print("Done")
        else:
            print("Could not extract details")

    # Step 3: Draft email (if we have event details and not enrich_only)
    if not enrich_only and event_details:
        print(f"   \u2709\ufe0f  Drafting outreach email...", end=" ", flush=True)

        # Use best available contact name
        best_contact = (
            result.enriched_contact_name
            or result.original_contact_name
        )

        email_data = draft_outreach_email(
            venue_name=name,
            contact_name=best_contact,
            highlights=highlights,
            event_details=event_details,
            private_events_url=result.private_events_url,
            config=config,
        )

        if email_data:
            result.email_subject = email_data.get("subject")
            result.email_body = email_data.get("body")
            print("Done")
        else:
            print("Failed")

    return result


def run_outreach_batch(
    pages: list[dict],
    config: Config,
    event_details: dict | None = None,
    enrich_only: bool = False,
    project_content: str | None = None,
) -> OutreachResult:
    """Run outreach pipeline on a batch of venues.

    Args:
        pages: List of Notion page dicts
        config: App config
        event_details: Event details dict (used for all venues)
        enrich_only: Skip email drafting
        project_content: Content from linked Team Project page
    """
    total = len(pages)
    enriched_venues = []
    enriched_count = 0
    drafted_count = 0

    print(f"\n\U0001f4e7 Running outreach on {total} venue(s)...\n")

    for i, page in enumerate(pages, 1):
        name = _extract_property_text(page, "Name")
        print(f"  [{i}/{total}] {name}")

        venue = run_outreach_for_venue(
            page, config,
            event_details=event_details,
            enrich_only=enrich_only,
            project_content=project_content,
        )
        enriched_venues.append(venue)

        # Count results
        if (venue.enriched_email or venue.enriched_contact_name or venue.enriched_phone):
            enriched_count += 1
        if venue.email_body:
            drafted_count += 1

        # Rate limit courtesy
        if i < total:
            time.sleep(2)

    # Summary
    print(f"\n\U0001f4ca Outreach Summary:")
    print(f"   \U0001f50d Enriched: {enriched_count}/{total}")
    if not enrich_only:
        print(f"   \u2709\ufe0f  Emails drafted: {drafted_count}/{total}")

    return OutreachResult(
        venues=enriched_venues,
        event_details=event_details,
        total_processed=total,
        total_enriched=enriched_count,
        total_emails_drafted=drafted_count,
    )
