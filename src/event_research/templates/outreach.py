"""Prompt templates for the outreach agent — contact enrichment + email drafting."""

from __future__ import annotations


# ---- Contact Enrichment ----

ENRICHMENT_SYSTEM_PROMPT = """\
You are a venue contact research specialist. Your job is to find the best \
contact information for reaching out to a venue about hosting a private event. \
Be thorough — search the venue's website, social media, event planning sites, \
and business directories to find the most direct contact for event inquiries.\
"""


def build_enrichment_prompt(
    venue_name: str,
    address: str,
    city: str,
    website: str | None,
) -> str:
    """Build the user prompt for contact enrichment."""

    prompt = (
        f"Find the private events contact information for this venue:\n\n"
        f"Name: {venue_name}\n"
        f"Address: {address}\n"
        f"City: {city}\n"
    )
    if website:
        prompt += f"Website: {website}\n"

    prompt += (
        "\nSearch for:\n"
        "1. The name and title of the person who handles private events, "
        "catering, or group dining inquiries\n"
        "2. A direct email address for event inquiries "
        "(events@, privateevents@, catering@ — not generic info@)\n"
        "3. A direct phone number or extension for events\n"
        "4. The URL of their private events or private dining page\n"
        "5. Any online booking or inquiry form URL\n\n"
        "Search the venue's own website first, then check event planning sites "
        "(The Venue Report, Peerspace, etc.), social media (LinkedIn for staff), "
        "and business directories.\n\n"
        "Return a JSON object:\n"
        "{\n"
        '  "contact_name": "Name of events coordinator or null",\n'
        '  "contact_title": "Their title or null",\n'
        '  "email": "events email or null",\n'
        '  "phone": "phone number or null",\n'
        '  "private_events_url": "URL to their private events page or null",\n'
        '  "booking_form_url": "URL to inquiry/booking form or null",\n'
        '  "enrichment_notes": "Brief summary of what you found and source quality",\n'
        '  "confidence": "high/medium/low"\n'
        "}\n\n"
        "Only include fields where you found actual information. "
        "Set others to null.\n"
        "Return ONLY the JSON object."
    )
    return prompt


# ---- Email Drafting ----

EMAIL_SYSTEM_PROMPT = """\
You are an expert at writing concise, professional outreach emails for \
corporate event inquiries. Your emails should be warm but businesslike, \
reference specific venue details that show you've done research, and \
clearly state what you need from the venue. Keep emails under 200 words.\
"""


def build_email_prompt(
    venue_name: str,
    contact_name: str | None,
    highlights: str | None,
    event_details: dict,
    private_events_url: str | None = None,
) -> str:
    """Build the prompt for drafting an outreach email.

    Args:
        venue_name: Name of the venue
        contact_name: Contact person's name (or None)
        highlights: Why this venue was selected
        event_details: Dict with keys like event_type, date, guest_count,
                       budget, vibe, audience, requirements
        private_events_url: URL to venue's private events page
    """

    prompt = "Draft a professional outreach email for a private event inquiry.\n\n"

    # Venue info
    prompt += "VENUE INFORMATION:\n"
    prompt += f"- Venue: {venue_name}\n"
    prompt += f"- Contact: {contact_name or 'Events Team'}\n"
    if highlights:
        prompt += f"- Why selected: {highlights}\n"
    if private_events_url:
        prompt += f"- Private events page: {private_events_url}\n"

    # Event details
    prompt += "\nEVENT DETAILS:\n"
    prompt += f"- Type: {event_details.get('event_type', 'Private event')}\n"
    prompt += f"- Date: {event_details.get('date', 'Flexible')}\n"
    prompt += f"- Guest count: {event_details.get('guest_count', 'TBD')}\n"
    prompt += f"- Budget: {event_details.get('budget', 'Flexible')}\n"
    if event_details.get("vibe"):
        prompt += f"- Vibe: {event_details['vibe']}\n"
    if event_details.get("audience"):
        prompt += f"- Audience: {event_details['audience']}\n"
    if event_details.get("requirements"):
        reqs = event_details["requirements"]
        if isinstance(reqs, list):
            reqs = ", ".join(reqs)
        prompt += f"- Requirements: {reqs}\n"

    # Instructions
    prompt += (
        "\nINSTRUCTIONS:\n"
        "- Address the contact by name if known, otherwise 'Hi there'\n"
        "- Reference why this venue caught our attention (use the highlights)\n"
        "- State the event type and key details naturally\n"
        "- Ask about: availability for the date, private space options, "
        "pricing/minimums"
    )

    # Add type-specific asks
    event_type = event_details.get("event_type", "").lower()
    if "dinner" in event_type:
        prompt += ", prix fixe or set menu options"
    elif "workshop" in event_type:
        prompt += ", AV setup, WiFi, and seating flexibility"
    elif "happy" in event_type:
        prompt += ", bar packages and standing room capacity"

    prompt += (
        "\n- Keep it under 200 words\n"
        "- Be warm and professional, not templated\n"
        "- Sign off with just a first name (the sender will fill in their own)\n\n"
        "Return JSON:\n"
        "{\n"
        '  "subject": "Email subject line",\n'
        '  "body": "Full email body"\n'
        "}\n\n"
        "Return ONLY the JSON object."
    )
    return prompt


# ---- Event Details Extraction ----

EVENT_DETAILS_EXTRACT_PROMPT = """\
Extract event planning details from this Notion project page content. \
Look for information about the event being planned — type, date, \
guest count, budget, vibe/atmosphere, target audience, and any specific \
requirements.

Return a JSON object with these fields (set to null if not found):
{
  "event_type": "dinner / happy_hour / workshop / other",
  "date": "date or date range",
  "guest_count": "number or range",
  "budget": "budget amount or range",
  "vibe": "atmosphere/vibe keywords",
  "audience": "who is attending",
  "requirements": ["list", "of", "requirements"]
}

Return ONLY the JSON object.

PAGE CONTENT:
"""
