"""Look up existing venues in Notion before doing external research.

This lets the agent reuse previously researched venues instead of
always searching from scratch.
"""

from __future__ import annotations

from notion_client import Client as NotionClient

from event_research.config import Config
from event_research.models import EventBrief, Venue
from event_research.notion_sync import get_notion_client
from event_research.health_check import _extract_property_text


def find_matching_venues(brief: EventBrief, config: Config) -> list[Venue]:
    """Search Notion for existing venues that match the event brief.

    Filters by:
      - City (exact match)
      - Event type in "Best For" (if available)
      - Not archived

    Returns Venue objects built from Notion data.
    """
    notion = get_notion_client(config)
    db_id = config.notion_database_id

    # Build filter
    filters = [
        {"property": "Status", "select": {"does_not_equal": "Archived"}},
        {"property": "City", "select": {"equals": brief.city}},
    ]

    # Add event type filter if we can
    # "Best For" is multi-select containing event types
    filters.append({
        "property": "Best For",
        "multi_select": {"contains": brief.event_type.value},
    })

    try:
        results = notion.databases.query(
            database_id=db_id,
            filter={"and": filters},
        )
    except Exception:
        # If the filter fails (e.g., city doesn't exist yet), return empty
        return []

    venues = []
    for page in results.get("results", []):
        venue = _page_to_venue(page)
        if venue:
            # If neighborhood is specified, filter loosely
            if brief.neighborhood:
                venue_neighborhood = venue.neighborhood.lower()
                brief_neighborhood = brief.neighborhood.lower()
                if brief_neighborhood not in venue_neighborhood and venue_neighborhood not in brief_neighborhood:
                    continue

            # If guest count specified, check capacity
            if brief.guest_count and venue.capacity_max:
                if venue.capacity_max < brief.guest_count:
                    continue

            venues.append(venue)

    return venues


def _page_to_venue(page: dict) -> Venue | None:
    """Convert a Notion page back into a Venue object."""
    try:
        name = _extract_property_text(page, "Name")
        if not name:
            return None

        # Extract checkbox values
        def get_checkbox(prop_name):
            prop = page.get("properties", {}).get(prop_name, {})
            return prop.get("checkbox") if prop.get("type") == "checkbox" else None

        # Extract number values
        def get_number(prop_name):
            prop = page.get("properties", {}).get(prop_name, {})
            return prop.get("number") if prop.get("type") == "number" else None

        # Extract multi-select
        def get_multi_select(prop_name):
            prop = page.get("properties", {}).get(prop_name, {})
            if prop.get("type") == "multi_select":
                return [opt.get("name", "") for opt in prop.get("multi_select", [])]
            return []

        return Venue(
            name=name,
            address=_extract_property_text(page, "Address") or "Unknown",
            neighborhood=_extract_property_text(page, "Neighborhood") or "Unknown",
            city=_extract_property_text(page, "City") or "Unknown",
            venue_type=_extract_property_text(page, "Venue Type") or "Unknown",
            website=_extract_property_text(page, "Website") or None,
            phone=_extract_property_text(page, "Phone") or None,
            email=_extract_property_text(page, "Email") or None,
            contact_name=_extract_property_text(page, "Contact Name") or None,
            price_range=_extract_property_text(page, "Price Range") or None,
            estimated_cost=_extract_property_text(page, "Estimated Cost") or None,
            capacity_min=get_number("Capacity Min"),
            capacity_max=get_number("Capacity Max"),
            private_space=get_checkbox("Private Space"),
            av_available=get_checkbox("AV Available"),
            outdoor_space=get_checkbox("Outdoor Space"),
            cuisine_or_style=_extract_property_text(page, "Cuisine / Style") or None,
            best_for=get_multi_select("Best For"),
            highlights=_extract_property_text(page, "Highlights") or None,
            source_url=_extract_property_text(page, "Source URL") or None,
            confidence=_extract_property_text(page, "Confidence").lower() or "medium",
        )
    except Exception:
        return None
