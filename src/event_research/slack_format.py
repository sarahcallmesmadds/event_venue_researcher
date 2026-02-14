"""Format research results as Slack Block Kit messages.

Converts ResearchResult into Slack-friendly blocks that can be posted
via the Slack API (through n8n or directly).
"""

from __future__ import annotations

from event_research.models import OutreachResult, ResearchResult, Venue


def format_results_for_slack(result: ResearchResult) -> list[dict]:
    """Convert a ResearchResult into Slack Block Kit blocks."""

    blocks = []

    # Header
    brief = result.brief
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"🔍 Venue Research: {brief.event_type.value.replace('_', ' ').title()} in {brief.city}",
        },
    })

    # Brief summary
    summary_parts = []
    if brief.neighborhood:
        summary_parts.append(f"📍 {brief.neighborhood}")
    if brief.budget:
        summary_parts.append(f"💰 {brief.budget}")
    if brief.guest_count:
        summary_parts.append(f"👥 {brief.guest_count} guests")
    if brief.vibe:
        summary_parts.append(f"✨ {brief.vibe}")
    if brief.audience:
        summary_parts.append(f"🎯 {brief.audience}")

    if summary_parts:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": " · ".join(summary_parts)}],
        })

    blocks.append({"type": "divider"})

    # Research notes
    if result.research_notes:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Research Notes:* {result.research_notes[:500]}",
            },
        })
        blocks.append({"type": "divider"})

    # Venues
    if not result.venues:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "No venues found. Try broadening your search criteria.",
            },
        })
        return blocks

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Found {len(result.venues)} venue(s):*",
        },
    })

    for i, venue in enumerate(result.venues, 1):
        blocks.extend(_format_venue_block(i, venue))

    return blocks


def _format_venue_block(index: int, venue: Venue) -> list[dict]:
    """Format a single venue as Slack blocks."""

    blocks = []

    # Venue name with link
    name_text = f"*{index}. {venue.name}*"
    if venue.website:
        name_text = f"*{index}. <{venue.website}|{venue.name}>*"

    # Build details text
    details = []
    details.append(f"📍 {venue.address}")
    if venue.venue_type:
        details.append(f"🏠 {venue.venue_type}")
    if venue.price_range:
        details.append(f"💰 {venue.price_range}")
    if venue.estimated_cost:
        details.append(f"💵 Est: {venue.estimated_cost}")
    if venue.capacity_min or venue.capacity_max:
        cap = f"👥 {venue.capacity_min or '?'}–{venue.capacity_max or '?'} guests"
        details.append(cap)

    # Features line
    features = []
    if venue.private_space:
        features.append("🔒 Private")
    if venue.av_available:
        features.append("🎥 AV")
    if venue.outdoor_space:
        features.append("🌿 Outdoor")
    if venue.cuisine_or_style:
        features.append(f"🍽️ {venue.cuisine_or_style}")
    if features:
        details.append(" · ".join(features))

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{name_text}\n{chr(10).join(details)}",
        },
    })

    # Highlights
    if venue.highlights:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"💡 _{venue.highlights}_",
            }],
        })

    # Contact info
    contact_parts = []
    if venue.phone:
        contact_parts.append(f"📞 {venue.phone}")
    if venue.email:
        contact_parts.append(f"📧 {venue.email}")
    if venue.contact_name:
        contact_parts.append(f"👤 {venue.contact_name}")

    if contact_parts:
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": " · ".join(contact_parts),
            }],
        })

    # Confidence badge
    confidence_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(venue.confidence, "⚪")
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"{confidence_emoji} Confidence: {venue.confidence}",
        }],
    })

    blocks.append({"type": "divider"})

    return blocks


def format_outreach_for_slack(result: OutreachResult) -> list[dict]:
    """Format outreach results for Slack — minimal output.

    Shows a quick summary with links to Notion + venue URL, price range,
    and location for each venue. Detailed info lives in Notion.
    """
    blocks = []

    if not result.venues:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "No venues processed for outreach.",
            },
        })
        return blocks

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"Outreach ready for {len(result.venues)} venue(s)",
        },
    })

    # Summary stats
    stats = f"Enriched: {result.total_enriched}/{result.total_processed}"
    if result.total_emails_drafted > 0:
        stats += f" | Emails drafted: {result.total_emails_drafted}"
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": stats}],
    })

    blocks.append({"type": "divider"})

    # Per-venue: quick-glance info
    for v in result.venues:
        # Venue name linked to website
        name_text = f"*{v.name}*"
        if v.website:
            name_text = f"*<{v.website}|{v.name}>*"

        # Quick details
        details = []
        if v.address:
            details.append(f"{v.address}")
        if v.price_range:
            details.append(f"{v.price_range}")

        # Contact info
        contact = v.enriched_contact_name or v.original_contact_name
        email = v.enriched_email or v.original_email
        phone = v.enriched_phone or v.original_phone
        contact_parts = []
        if contact:
            contact_parts.append(contact)
        if email:
            contact_parts.append(email)
        elif phone:
            contact_parts.append(phone)

        line = name_text
        if details:
            line += f"\n{' · '.join(details)}"
        if contact_parts:
            line += f"\n{' · '.join(contact_parts)}"

        # Notion link
        if v.notion_url:
            line += f"\n<{v.notion_url}|View in Notion>"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": line},
        })

    return blocks
