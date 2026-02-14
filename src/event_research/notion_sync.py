"""Notion integration — push venue results, check for duplicates, archive stale venues.

Also handles outreach updates (enriched contacts, email drafts, status changes).
"""

from __future__ import annotations

from datetime import date

from notion_client import Client as NotionClient

from event_research.config import Config
from event_research.models import EnrichedVenue, Venue, ResearchResult


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


# ---- Outreach functions ----

def get_venues_for_outreach(
    config: Config,
    city: str | None = None,
    venue_name: str | None = None,
    status_filter: list[str] | None = None,
) -> list[dict]:
    """Query venues that are ready for outreach.

    Args:
        config: App config
        city: Filter by city (exact match)
        venue_name: Filter by venue name (contains match)
        status_filter: Status values to include (default: New, Ready for Outreach)
    """
    notion = get_notion_client(config)

    if status_filter is None:
        status_filter = ["New", "Ready for Outreach"]

    # Build filter
    filters = []

    # Status filter (OR across allowed statuses)
    if len(status_filter) == 1:
        filters.append({
            "property": "Status",
            "select": {"equals": status_filter[0]},
        })
    else:
        filters.append({
            "or": [
                {"property": "Status", "select": {"equals": s}}
                for s in status_filter
            ]
        })

    # City filter
    if city:
        filters.append({
            "property": "City",
            "select": {"equals": city},
        })

    # Venue name filter (title contains)
    if venue_name:
        filters.append({
            "property": "Name",
            "title": {"contains": venue_name},
        })

    # Combine filters
    query_filter = {"and": filters} if len(filters) > 1 else filters[0] if filters else None

    all_pages = []
    start_cursor = None

    while True:
        kwargs = {"database_id": config.notion_database_id}
        if query_filter:
            kwargs["filter"] = query_filter
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        try:
            results = notion.databases.query(**kwargs)
        except Exception:
            return []

        all_pages.extend(results["results"])

        if not results.get("has_more"):
            break
        start_cursor = results.get("next_cursor")

    return all_pages


def get_venue_by_page_id(config: Config, page_id: str) -> dict | None:
    """Fetch a single venue page by its Notion page ID."""
    notion = get_notion_client(config)
    try:
        return notion.pages.retrieve(page_id=page_id)
    except Exception as e:
        print(f"  \u274c Failed to fetch page {page_id}: {e}")
        return None


def get_linked_project_content(config: Config, venue_page: dict) -> str | None:
    """If the venue has a 'Team Projects' relation, fetch the linked project's content.

    Returns the project page content as plain text, or None if no relation exists.
    """
    notion = get_notion_client(config)

    # Check if "Team Projects" relation property exists
    relation_prop = venue_page.get("properties", {}).get("Team Projects", {})
    if relation_prop.get("type") != "relation":
        return None

    related_pages = relation_prop.get("relation", [])
    if not related_pages:
        return None

    # Fetch the first linked project page
    project_id = related_pages[0].get("id")
    if not project_id:
        return None

    try:
        # Fetch the page blocks (content)
        blocks = notion.blocks.children.list(block_id=project_id)
        text_parts = []
        for block in blocks.get("results", []):
            block_type = block.get("type", "")
            block_data = block.get(block_type, {})

            # Extract text from rich_text arrays in various block types
            rich_texts = block_data.get("rich_text", [])
            for rt in rich_texts:
                plain_text = rt.get("plain_text", "")
                if plain_text:
                    text_parts.append(plain_text)

            # Also check for "text" in some block types
            if "text" in block_data:
                for rt in block_data["text"]:
                    plain_text = rt.get("plain_text", "")
                    if plain_text:
                        text_parts.append(plain_text)

        return "\n".join(text_parts) if text_parts else None

    except Exception as e:
        print(f"  \u26a0\ufe0f  Failed to fetch project content: {e}")
        return None


def update_venue_outreach(
    notion: NotionClient,
    page_id: str,
    enriched: EnrichedVenue,
) -> None:
    """Update a venue's Notion page with enriched contact data and email draft."""
    properties: dict = {}

    # Update contact info (only if enriched data is better than original)
    if enriched.enriched_contact_name:
        properties["Contact Name"] = {
            "rich_text": [{"text": {"content": enriched.enriched_contact_name}}]
        }
    if enriched.enriched_contact_title:
        properties["Contact Title"] = {
            "rich_text": [{"text": {"content": enriched.enriched_contact_title}}]
        }
    if enriched.enriched_email:
        properties["Email"] = {"email": enriched.enriched_email}
    if enriched.enriched_phone:
        properties["Phone"] = {"phone_number": enriched.enriched_phone}
    if enriched.private_events_url:
        properties["Private Events URL"] = {"url": enriched.private_events_url}
    if enriched.booking_form_url:
        properties["Booking Form URL"] = {"url": enriched.booking_form_url}

    # Email draft (truncate to 2000 chars for Notion rich_text limit)
    if enriched.email_body:
        email_text = enriched.email_body[:2000]
        if enriched.email_subject:
            email_text = f"Subject: {enriched.email_subject}\n\n{email_text}"
            email_text = email_text[:2000]
        properties["Outreach Email"] = {
            "rich_text": [{"text": {"content": email_text}}]
        }

    # Outreach date
    properties["Outreach Date"] = {
        "date": {"start": date.today().isoformat()}
    }

    # Contact method (prioritize: email > form > phone > website)
    if enriched.enriched_email or enriched.original_email:
        method = "Email"
    elif enriched.booking_form_url:
        method = "Form"
    elif enriched.enriched_phone or enriched.original_phone:
        method = "Phone"
    else:
        method = "Website"
    properties["Contact Method"] = {"select": {"name": method}}

    # Advance status to Ready for Outreach
    properties["Status"] = {"select": {"name": "Ready for Outreach"}}

    if properties:
        try:
            notion.pages.update(page_id=page_id, properties=properties)
            print(f"      \U0001f4dd Updated in Notion: {', '.join(properties.keys())}")
        except Exception as e:
            print(f"      \u26a0\ufe0f  Failed to update Notion: {e}")


def update_date_last_checked(notion: NotionClient, page_id: str) -> None:
    """Set the Date Last Checked property to today."""
    try:
        notion.pages.update(
            page_id=page_id,
            properties={
                "Date Last Checked": {
                    "date": {"start": date.today().isoformat()}
                }
            },
        )
    except Exception as e:
        # Silently skip if property doesn't exist yet
        pass


def advance_venue_status(notion: NotionClient, page_id: str, new_status: str) -> None:
    """Set a venue's status to a new value."""
    valid = {"New", "Ready for Outreach", "Contacted", "Responded", "Confirmed", "Rejected", "Archived"}
    if new_status not in valid:
        print(f"  \u26a0\ufe0f  Invalid status '{new_status}'. Must be one of: {valid}")
        return
    try:
        notion.pages.update(
            page_id=page_id,
            properties={"Status": {"select": {"name": new_status}}},
        )
    except Exception as e:
        print(f"  \u274c Failed to update status: {e}")
