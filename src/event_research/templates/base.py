"""Research prompt templates for each event type.

Each template tells the agent what to prioritize, what questions to answer,
and what kind of venues to look for based on the event type.
"""

from event_research.models import EventBrief, EventType

# ----- Shared preamble for all event types -----

SYSTEM_PROMPT = """\
You are an expert event venue researcher. A company is hosting an event and needs \
venue recommendations. Your job is to find specific, real venues that match their \
criteria and return detailed, actionable information.

IMPORTANT RULES:
- Only recommend REAL venues that you are confident exist. Do not invent venues.
- Include as much contact info as possible (phone, email, website, contact name).
- Be specific about pricing — ranges are fine, but "varies" is not helpful.
- Note if a venue has a private room, event space, or buyout option.
- If you're unsure about a detail, say so and mark confidence as "low".
- Prioritize venues that are KNOWN for hosting the type of event requested.
- Consider the audience — a CMO dinner is different from an engineering team offsite.
"""

# ----- Per-event-type research guidance -----

EVENT_TYPE_GUIDANCE: dict[EventType, str] = {
    EventType.DINNER: """\
EVENT TYPE: Hosted Dinner

RESEARCH PRIORITIES (in order):
1. Private dining rooms or semi-private spaces — this is non-negotiable for a hosted dinner
2. Cuisine quality and reputation — the food IS the event
3. Ambiance / atmosphere that matches the stated vibe
4. Appropriate capacity for the guest count (not too big, not too cramped)
5. Prix fixe or set menu options (easier for corporate budgeting)
6. Wine/beverage program quality

WHAT TO LOOK FOR:
- Restaurants with dedicated private dining rooms (PDR)
- Upscale restaurants that do full or partial buyouts
- Chef's table experiences
- Members-only clubs with dining (Soho House, Core Club, etc.)
- Hotel restaurants with private event spaces

BUDGET CONSIDERATIONS:
- Factor in: food, beverage, tax, gratuity (usually 20-22%), room fee if any
- Typical corporate dinner: $150-400pp all-in depending on city/tier
- Note minimum spend requirements — many PDRs have them

AVOID:
- Venues primarily known as "event spaces" (too sterile for dinner)
- Large banquet halls (wrong vibe for intimate dinners)
- Chain restaurants
""",

    EventType.HAPPY_HOUR: """\
EVENT TYPE: Happy Hour / Cocktail Reception

RESEARCH PRIORITIES (in order):
1. Bar quality and cocktail program
2. Standing room / mingling-friendly layout
3. Vibe and energy — should feel fun and social, not stuffy
4. Passed apps or bar snacks availability
5. Location convenience (walkable from offices, transit-friendly)
6. Outdoor or rooftop options if weather permits

WHAT TO LOOK FOR:
- Cocktail bars with semi-private or private areas
- Rooftop bars with event buyout options
- Speakeasies or unique concept bars
- Hotel bars with reserved sections
- Breweries/taprooms with event spaces
- Wine bars with standing room areas

BUDGET CONSIDERATIONS:
- Factor in: drinks (open bar vs drink tickets), passed apps, tax, gratuity
- Typical corporate happy hour: $75-150pp for 2-3 hours
- Ask about: consumption-based vs flat-rate bar packages
- Note minimum spend requirements

AVOID:
- Sit-down-only restaurants (wrong format)
- Dive bars (unless that's the stated vibe)
- Venues with poor acoustics / too loud to network
""",

    EventType.WORKSHOP: """\
EVENT TYPE: Workshop / Working Session

RESEARCH PRIORITIES (in order):
1. AV setup — screens, projectors, whiteboards, good WiFi
2. Flexible seating arrangements (classroom, U-shape, rounds)
3. Natural light and comfortable environment
4. Breakout room availability for small group work
5. Catering options (working lunch, coffee service)
6. Location convenience and ease of finding the venue

WHAT TO LOOK FOR:
- Boutique meeting spaces (Convene, Industrious, etc.)
- Hotel meeting rooms (not ballrooms — too big and sterile)
- Creative co-working spaces with event rooms
- Innovation labs or startup spaces that rent out
- Loft spaces with AV capabilities
- Gallery spaces that can be configured for working sessions

BUDGET CONSIDERATIONS:
- Factor in: room rental, AV rental, catering, coffee/beverage service
- Typical half-day workshop: $100-250pp including F&B
- Typical full-day workshop: $200-400pp including F&B
- Note: some spaces include AV in rental, others charge extra
- Ask about day rate vs hourly

AVOID:
- Traditional conference centers (too corporate / sterile)
- Restaurants (wrong setup for working)
- Venues without reliable WiFi
- Spaces with fixed seating / no flexibility
""",
}


def build_research_prompt(brief: EventBrief) -> str:
    """Build the full user prompt for the research agent from an EventBrief."""

    guidance = EVENT_TYPE_GUIDANCE[brief.event_type]

    parts = [
        guidance,
        "\n--- EVENT BRIEF ---\n",
        f"Event Type: {brief.event_type.value}",
        f"City: {brief.city}",
    ]

    if brief.neighborhood:
        parts.append(f"Neighborhood/Area: {brief.neighborhood}")
    if brief.budget:
        parts.append(f"Budget: {brief.budget}")
    if brief.guest_count:
        parts.append(f"Guest Count: {brief.guest_count}")
    if brief.vibe:
        parts.append(f"Vibe/Atmosphere: {brief.vibe}")
    if brief.audience:
        parts.append(f"Audience: {brief.audience}")
    if brief.requirements:
        parts.append(f"Must-Haves: {', '.join(brief.requirements)}")
    if brief.keywords:
        parts.append(f"Keywords/Preferences: {', '.join(brief.keywords)}")
    if brief.date_range:
        parts.append(f"Target Date: {brief.date_range}")
    if brief.notes:
        parts.append(f"Additional Notes: {brief.notes}")

    parts.append("\n--- INSTRUCTIONS ---")
    parts.append(
        "Research and recommend up to 8 venues that match this brief. "
        "For each venue, use the web search tool to find and verify: "
        "the venue's website, phone number, email, private event contact, "
        "pricing details, capacity, and any relevant details.\n\n"
        "After researching, return your results as a JSON object with this exact structure:\n"
        "{\n"
        '  "venues": [\n'
        "    {\n"
        '      "name": "Venue Name",\n'
        '      "address": "Full street address",\n'
        '      "neighborhood": "Neighborhood name",\n'
        '      "city": "City",\n'
        '      "venue_type": "e.g. restaurant - private dining",\n'
        '      "website": "https://...",\n'
        '      "phone": "phone number",\n'
        '      "email": "events@ or contact email",\n'
        '      "contact_name": "Events manager name if found",\n'
        '      "price_range": "e.g. $$$, $150-200pp",\n'
        '      "estimated_cost": "e.g. $4,500 for 20 guests",\n'
        '      "capacity_min": 10,\n'
        '      "capacity_max": 40,\n'
        '      "private_space": true,\n'
        '      "av_available": false,\n'
        '      "outdoor_space": true,\n'
        '      "cuisine_or_style": "e.g. Modern American, Italian",\n'
        '      "best_for": ["dinner", "happy_hour"],\n'
        '      "highlights": "1-2 sentence pitch for why this venue fits the brief",\n'
        '      "source_url": "URL where you found/verified info",\n'
        '      "confidence": "high"\n'
        "    }\n"
        "  ],\n"
        '  "research_notes": "Brief summary of your research process and any caveats"\n'
        "}\n\n"
        "Return ONLY the JSON object, no other text."
    )

    return "\n".join(parts)
