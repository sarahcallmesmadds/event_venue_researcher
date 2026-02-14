"""Data models for event research requests and venue results."""

from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class EventType(str, Enum):
    DINNER = "dinner"
    HAPPY_HOUR = "happy_hour"
    WORKSHOP = "workshop"


class EventBrief(BaseModel):
    """The intake: everything the user tells us about the event they want to host."""

    event_type: EventType
    city: str
    neighborhood: str | None = None
    budget: str | None = None  # e.g. "$5,000", "under $3k per person"
    guest_count: int | None = None
    vibe: str | None = None  # e.g. "intimate, upscale", "casual rooftop"
    audience: str | None = None  # e.g. "CMOs", "engineering leaders"
    requirements: list[str] = Field(default_factory=list)  # e.g. ["private room", "AV setup"]
    keywords: list[str] = Field(default_factory=list)  # e.g. ["farm-to-table", "speakeasy"]
    date_range: str | None = None  # e.g. "March 2025", "Q2"
    notes: str | None = None  # any extra context


class Venue(BaseModel):
    """A single venue recommendation returned by the research agent."""

    name: str
    address: str
    neighborhood: str
    city: str
    venue_type: str  # e.g. "restaurant - private dining", "event space"
    website: str | None = None
    phone: str | None = None
    email: str | None = None
    contact_name: str | None = None
    price_range: str | None = None  # e.g. "$$$", "$150-200pp"
    estimated_cost: str | None = None  # e.g. "$4,500 for 20 guests"
    capacity_min: int | None = None
    capacity_max: int | None = None
    private_space: bool | None = None
    av_available: bool | None = None
    outdoor_space: bool | None = None
    cuisine_or_style: str | None = None
    best_for: list[str] = Field(default_factory=list)  # e.g. ["dinner", "happy_hour"]
    highlights: str | None = None  # 1-2 sentence pitch for why this venue fits
    source_url: str | None = None  # where we found/validated the info
    confidence: str = "medium"  # low / medium / high — how sure we are about the data


class ResearchResult(BaseModel):
    """The full output of a research run."""

    brief: EventBrief
    venues: list[Venue] = Field(default_factory=list)
    research_notes: str | None = None  # agent's summary / thinking


class EnrichedVenue(BaseModel):
    """A venue with enriched contact data and an optional outreach email draft."""

    # Core identity (from Notion)
    name: str
    city: str
    page_id: str | None = None
    notion_url: str | None = None

    # Original contact info (before enrichment)
    original_email: str | None = None
    original_phone: str | None = None
    original_contact_name: str | None = None

    # Enriched contact info
    enriched_email: str | None = None
    enriched_phone: str | None = None
    enriched_contact_name: str | None = None
    enriched_contact_title: str | None = None  # e.g. "Events Director"
    private_events_url: str | None = None
    booking_form_url: str | None = None
    enrichment_confidence: str = "medium"
    enrichment_notes: str | None = None

    # Email draft
    email_subject: str | None = None
    email_body: str | None = None

    # Venue context (for display / Slack)
    highlights: str | None = None
    website: str | None = None
    price_range: str | None = None
    address: str | None = None
    neighborhood: str | None = None


class OutreachResult(BaseModel):
    """Result of running outreach on one or more venues."""

    venues: list[EnrichedVenue] = Field(default_factory=list)
    event_details: dict | None = None  # extracted from Team Project page
    total_processed: int = 0
    total_enriched: int = 0  # had new contact info found
    total_emails_drafted: int = 0
    notes: str | None = None
