"""Core research agent — uses Claude with web search to find venues.

Uses an agentic loop so Claude can do multiple rounds of web searching
before producing the final structured response.
"""

from __future__ import annotations

import json
import re
import time
import anthropic

from event_research.config import Config
from event_research.models import EventBrief, Venue, ResearchResult
from event_research.templates.base import SYSTEM_PROMPT, build_research_prompt


# Web search tool definition for Claude
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 30,
}

MAX_TURNS = 15  # Safety limit on agentic loop iterations


def _call_with_retry(client, model, messages, max_retries=3):
    """Call the API with automatic retry on rate limit errors."""
    for attempt in range(max_retries):
        try:
            return client.messages.create(
                model=model,
                max_tokens=8000,
                system=SYSTEM_PROMPT,
                tools=[WEB_SEARCH_TOOL],
                messages=messages,
            )
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"   ⏳ Rate limited — waiting {wait}s before retry ({attempt + 1}/{max_retries})...")
            time.sleep(wait)
    # Final attempt without catching
    return client.messages.create(
        model=model,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=messages,
    )


def run_research(brief: EventBrief, config: Config, skip_notion_lookup: bool = False) -> ResearchResult:
    """Run the research agent for a given event brief.

    First checks Notion for existing matching venues, then searches the web
    for additional recommendations.
    """
    # Step 0: Check Notion for existing matches
    existing_venues = []
    if not skip_notion_lookup and config.notion_database_id and config.notion_api_key:
        try:
            from event_research.notion_lookup import find_matching_venues
            existing_venues = find_matching_venues(brief, config)
            if existing_venues:
                print(f"\n📋 Found {len(existing_venues)} existing venue(s) in Notion that match")
        except Exception as e:
            print(f"\n⚠️  Notion lookup failed (continuing with web search): {e}")

    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    user_prompt = build_research_prompt(brief)

    # If we have existing venues, tell the agent about them so it doesn't re-research
    if existing_venues:
        existing_names = [v.name for v in existing_venues]
        user_prompt += (
            f"\n\nNOTE: We already have these venues in our database for this area. "
            f"Do NOT include them in your results — find NEW venues instead:\n"
            f"{', '.join(existing_names)}"
        )

    print(f"\n🔍 Researching {brief.event_type.value} venues in {brief.city}...")
    if brief.neighborhood:
        print(f"   Neighborhood: {brief.neighborhood}")
    if brief.budget:
        print(f"   Budget: {brief.budget}")
    if brief.guest_count:
        print(f"   Guests: {brief.guest_count}")
    print(f"   Searching (this may take 1-2 minutes)...\n")

    messages = [{"role": "user", "content": user_prompt}]

    # Agentic loop — keep going until Claude stops using tools
    for turn in range(MAX_TURNS):
        response = _call_with_retry(client, config.model, messages)


        # If Claude is done (no more tool use), break
        if response.stop_reason == "end_turn":
            print(f"   ✅ Research complete ({turn + 1} turn(s))")
            break

        # Otherwise, Claude used tools — add its response and continue
        # The response content includes both text and tool_use/server_tool_use blocks
        messages.append({"role": "assistant", "content": response.content})

        # Build tool results for any tool uses in the response
        # For web_search (server-side tool), results are already in the response
        # We just need to keep the conversation going
        tool_results = []
        for block in response.content:
            if block.type == "web_search_tool_result":
                # Server-side tool results are already handled by the API
                # We include them back so Claude sees its own search results
                tool_results.append(block)

        if tool_results:
            messages.append({"role": "user", "content": tool_results})
            search_count = sum(1 for b in response.content if b.type == "server_tool_use")
            print(f"   🔎 Turn {turn + 1}: {search_count} web search(es)...")
        else:
            # No tool results to feed back — model may have stopped with tool_use
            # but without server tool results. Just break.
            print(f"   ⚠️  Turn {turn + 1}: No search results returned, finishing...")
            break
    else:
        print(f"   ⚠️  Hit max turns ({MAX_TURNS}), returning what we have...")

    result = _parse_response(response, brief)

    # Combine existing Notion venues with new research results
    if existing_venues:
        # Put existing venues first, labeled so the user knows
        for v in existing_venues:
            v.highlights = f"[From existing database] {v.highlights or ''}"
        result.venues = existing_venues + result.venues
        if result.research_notes:
            result.research_notes = (
                f"Found {len(existing_venues)} existing venue(s) in Notion + "
                f"{len(result.venues) - len(existing_venues)} new from web search. "
                + result.research_notes
            )

    return result


def _parse_response(response: anthropic.types.Message, brief: EventBrief) -> ResearchResult:
    """Parse Claude's response into structured ResearchResult."""

    # Collect ALL text blocks from the response (there may be multiple)
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)

    text_content = "\n".join(text_parts) if text_parts else None

    if not text_content:
        return ResearchResult(
            brief=brief,
            research_notes="Agent returned no text response. This is unexpected.",
        )

    # Try to extract JSON from the response
    data = _extract_json(text_content)
    if data is None:
        return ResearchResult(
            brief=brief,
            research_notes=f"Could not parse agent response as JSON. Raw response:\n{text_content[:3000]}",
        )

    # Parse venues
    venues = []
    for v in data.get("venues", []):
        try:
            venue = Venue(
                name=v.get("name", "Unknown"),
                address=v.get("address", "Unknown"),
                neighborhood=v.get("neighborhood", brief.neighborhood or "Unknown"),
                city=v.get("city", brief.city),
                venue_type=v.get("venue_type", "Unknown"),
                website=v.get("website"),
                phone=v.get("phone"),
                email=v.get("email"),
                contact_name=v.get("contact_name"),
                price_range=v.get("price_range"),
                estimated_cost=v.get("estimated_cost"),
                capacity_min=v.get("capacity_min"),
                capacity_max=v.get("capacity_max"),
                private_space=v.get("private_space"),
                av_available=v.get("av_available"),
                outdoor_space=v.get("outdoor_space"),
                cuisine_or_style=v.get("cuisine_or_style"),
                best_for=v.get("best_for", [brief.event_type.value]),
                highlights=_strip_citations(v.get("highlights", "")) or None,
                source_url=v.get("source_url"),
                confidence=v.get("confidence", "medium"),
            )
            venues.append(venue)
        except Exception as e:
            print(f"  ⚠️  Skipped venue due to parse error: {e}")

    return ResearchResult(
        brief=brief,
        venues=venues,
        research_notes=data.get("research_notes"),
    )


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
    """Remove <cite index="...">...</cite> tags, keeping the inner text."""
    return re.sub(r'<cite[^>]*>(.*?)</cite>', r'\1', text, flags=re.DOTALL)
