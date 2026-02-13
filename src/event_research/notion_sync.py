"""Notion integration — push venue results, check for duplicates, archive stale venues."""

from __future__ import annotations

from notion_client import Client as NotionClient

from event_research.config import Config
from event_research.models import Venue, ResearchResult


def get_notion_client(config: Config) -> NotionClient:
    return NotionClient(auth=config.notion_api_key)


def push_results_to_notion(result: ResearchResult, config: Config) -> list[str]:
    """Push venue results to Notion database. Returns list of created page URLs."""

    notion = get_notion_client(config)
    db_id = config.notion_database_id
    created_urls = []

    for venue in result.venues:
        # Check if venue already exists (by name + city)
        existing = _find_existing_venue(notion, db_id, venue.name, venue.city)
        if existing:
            print(f"  ⏭️  '{venue.name}' already in Notion — skipping")
            continue

        # Build Notion page properties
        properties = _venue_to_notion_properties(venue, result.brief.event_type.value)

        try:
            page = notion.pages.create(
                parent={"database_id": db_id},
                properties=properties,
            )
            url = page.get("url", "")
            created_urls.append(url)
            print(f"  ✅ Added '{venue.name}' to Notion")
        except Exception as e:
            print(f"  ❌ Failed to add '{venue.name}': {e}")

    return created_urls


def _venue_to_notion_properties(venue: Venue, event_type: str) -> dict:
    """Convert a Venue model to Notion page properties."""

    props: dict = {
        "Name": {"title": [{"text": {"content": venue.name}}]},
        "Address": {"rich_text": [{"text": {"content": venue.address}}]},
        "Neighborhood": {"rich_text": [{"text": {"content": venue.neighborhood}}]},
        "City": {"select": {"name": venue.city}},
        "Venue Type": {"rich_text": [{"text": {"content": venue.venue_type}}]},
        "Status": {"select": {"name": "New"}},
        "Confidence": {"select": {"name": venue.confidence.capitalize()}},
    }

    # Best For — multi-select
    if venue.best_for:
        props["Best For"] = {
            "multi_select": [{"name": t} for t in venue.best_for]
        }

    # Researched For Event Type
    props["Researched For"] = {"select": {"name": event_type}}

    # Optional text fields
    if venue.website:
        props["Website"] = {"url": venue.website}
    if venue.phone:
        props["Phone"] = {"phone_number": venue.phone}
    if venue.email:
        props["Email"] = {"email": venue.email}
    if venue.contact_name:
        props["Contact Name"] = {"rich_text": [{"text": {"content": venue.contact_name}}]}
    if venue.price_range:
        props["Price Range"] = {"rich_text": [{"text": {"content": venue.price_range}}]}
    if venue.estimated_cost:
        props["Estimated Cost"] = {"rich_text": [{"text": {"content": venue.estimated_cost}}]}
    if venue.capacity_min is not None:
        props["Capacity Min"] = {"number": venue.capacity_min}
    if venue.capacity_max is not None:
        props["Capacity Max"] = {"number": venue.capacity_max}
    if venue.cuisine_or_style:
        props["Cuisine / Style"] = {"rich_text": [{"text": {"content": venue.cuisine_or_style}}]}
    if venue.highlights:
        props["Highlights"] = {"rich_text": [{"text": {"content": venue.highlights}}]}
    if venue.source_url:
        props["Source URL"] = {"url": venue.source_url}

    # Boolean fields
    if venue.private_space is not None:
        props["Private Space"] = {"checkbox": venue.private_space}
    if venue.av_available is not None:
        props["AV Available"] = {"checkbox": venue.av_available}
    if venue.outdoor_space is not None:
        props["Outdoor Space"] = {"checkbox": venue.outdoor_space}

    return props


def _find_existing_venue(
    notion: NotionClient, db_id: str, name: str, city: str
) -> dict | None:
    """Check if a venue with the same name + city already exists."""
    try:
        results = notion.databases.query(
            database_id=db_id,
            filter={
                "and": [
                    {"property": "Name", "title": {"equals": name}},
                    {"property": "City", "select": {"equals": city}},
                ]
            },
        )
        if results["results"]:
            return results["results"][0]
    except Exception:
        pass
    return None


def archive_venue(notion: NotionClient, page_id: str) -> None:
    """Archive a venue by setting its status to Archived."""
    try:
        notion.pages.update(
            page_id=page_id,
            properties={"Status": {"select": {"name": "Archived"}}},
        )
    except Exception as e:
        print(f"  ❌ Failed to archive venue: {e}")


def get_all_venues(config: Config) -> list[dict]:
    """Fetch all non-archived venues from the Notion database."""
    notion = get_notion_client(config)
    all_pages = []
    start_cursor = None

    while True:
        kwargs = {
            "database_id": config.notion_database_id,
            "filter": {
                "property": "Status",
                "select": {"does_not_equal": "Archived"},
            },
        }
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        results = notion.databases.query(**kwargs)
        all_pages.extend(results["results"])

        if not results.get("has_more"):
            break
        start_cursor = results.get("next_cursor")

    return all_pages
