"""Core research agent — uses Claude with web search to find venues."""

from __future__ import annotations

import json
import anthropic

from event_research.config import Config
from event_research.models import EventBrief, Venue, ResearchResult
from event_research.templates.base import SYSTEM_PROMPT, build_research_prompt


# Web search tool definition for Claude
WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 20,
}


def run_research(brief: EventBrief, config: Config) -> ResearchResult:
    """Run the research agent for a given event brief.

    Sends the brief to Claude with web search enabled.
    Claude will search for real venues, verify details, and return structured results.
    """
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    user_prompt = build_research_prompt(brief)

    print(f"\n🔍 Researching {brief.event_type.value} venues in {brief.city}...")
    if brief.neighborhood:
        print(f"   Neighborhood: {brief.neighborhood}")
    if brief.budget:
        print(f"   Budget: {brief.budget}")
    if brief.guest_count:
        print(f"   Guests: {brief.guest_count}")
    print(f"   Searching (this may take 30-60 seconds)...\n")

    response = client.messages.create(
        model=config.model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        tools=[WEB_SEARCH_TOOL],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Extract the final text response (after all tool use)
    return _parse_response(response, brief)


def _parse_response(response: anthropic.types.Message, brief: EventBrief) -> ResearchResult:
    """Parse Claude's response into structured ResearchResult."""

    # Find the text block in the response
    text_content = None
    for block in response.content:
        if block.type == "text":
            text_content = block.text
            break

    if not text_content:
        return ResearchResult(
            brief=brief,
            research_notes="Agent returned no text response. This is unexpected.",
        )

    # Try to extract JSON from the response
    try:
        # Handle case where JSON is wrapped in markdown code blocks
        cleaned = text_content.strip()
        if cleaned.startswith("```"):
            # Remove markdown code fences
            lines = cleaned.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        start = text_content.find("{")
        end = text_content.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(text_content[start:end])
            except json.JSONDecodeError:
                return ResearchResult(
                    brief=brief,
                    research_notes=f"Could not parse agent response as JSON. Raw response:\n{text_content[:2000]}",
                )
        else:
            return ResearchResult(
                brief=brief,
                research_notes=f"No JSON found in agent response. Raw response:\n{text_content[:2000]}",
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
                highlights=v.get("highlights"),
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
