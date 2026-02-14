"""FastAPI wrapper for the event research agent.

Exposes the research agent as an HTTP API that n8n (or any client) can call.

POST /research  — run venue research for an event brief
GET  /health    — health check
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

from event_research.config import load_config
from event_research.models import EventBrief, EventType, ResearchResult
from event_research.agent import run_research
from event_research.notion_sync import push_results_to_notion
from event_research.slack_format import format_results_for_slack


# ---- Request / Response models ----

class ResearchRequest(BaseModel):
    """Incoming research request from n8n / Slack."""

    event_type: str  # "dinner", "happy_hour", "workshop"
    city: str
    neighborhood: str | None = None
    budget: str | None = None
    guest_count: int | None = None
    vibe: str | None = None
    audience: str | None = None
    requirements: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    date_range: str | None = None
    notes: str | None = None
    push_to_notion: bool = True
    slack_format: bool = True  # return Slack Block Kit format
    new_only: bool = False  # skip Notion lookup, only return new web results


class ResearchResponse(BaseModel):
    """Response back to n8n / Slack."""

    status: str  # "success" or "error"
    venue_count: int = 0
    research_notes: str | None = None
    venues: list[dict] = Field(default_factory=list)
    slack_blocks: list[dict] | None = None  # Slack Block Kit blocks
    notion_urls: list[str] = Field(default_factory=list)
    error: str | None = None


# ---- App ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate config on startup
    config = load_config()
    missing = config.validate_keys()
    if "ANTHROPIC_API_KEY" in missing:
        print("⚠️  WARNING: ANTHROPIC_API_KEY not set — research will fail")
    yield


app = FastAPI(
    title="Event Venue Research Agent",
    version="0.1.0",
    lifespan=lifespan,
)

# Simple API key auth — set API_SECRET env var to require it
API_SECRET = os.getenv("API_SECRET", "")


def _check_auth(authorization: str | None):
    """Check API key if API_SECRET is configured."""
    if not API_SECRET:
        return  # no auth required
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    # Accept "Bearer <token>" or just "<token>"
    token = authorization.replace("Bearer ", "").strip()
    if token != API_SECRET:
        raise HTTPException(status_code=403, detail="Invalid API key")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "event-research-agent"}


@app.post("/research", response_model=ResearchResponse)
async def research(
    request: ResearchRequest,
    authorization: str | None = Header(default=None),
):
    """Run venue research for an event brief."""

    _check_auth(authorization)

    # Validate event type
    try:
        event_type = EventType(request.event_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event_type: '{request.event_type}'. Must be one of: dinner, happy_hour, workshop",
        )

    config = load_config()

    # Build the brief
    brief = EventBrief(
        event_type=event_type,
        city=request.city,
        neighborhood=request.neighborhood,
        budget=request.budget,
        guest_count=request.guest_count,
        vibe=request.vibe,
        audience=request.audience,
        requirements=request.requirements,
        keywords=request.keywords,
        date_range=request.date_range,
        notes=request.notes,
    )

    # Run research (this is synchronous and takes 30-120s)
    try:
        result = run_research(brief, config, skip_notion_lookup=request.new_only)
    except Exception as e:
        return ResearchResponse(
            status="error",
            error=f"Research failed: {str(e)}",
        )

    # Push to Notion if requested
    notion_urls = []
    if request.push_to_notion and result.venues:
        missing = config.validate_keys()
        if "NOTION_API_KEY" not in missing and "NOTION_DATABASE_ID" not in missing:
            try:
                notion_urls = push_results_to_notion(result, config)
            except Exception as e:
                print(f"Notion push failed: {e}")

    # Format for Slack if requested
    slack_blocks = None
    if request.slack_format:
        slack_blocks = format_results_for_slack(result)

    return ResearchResponse(
        status="success",
        venue_count=len(result.venues),
        research_notes=result.research_notes,
        venues=[v.dict() for v in result.venues],
        slack_blocks=slack_blocks,
        notion_urls=notion_urls,
    )


# ---- Parse natural language into structured request (using Claude) ----

PARSE_SYSTEM_PROMPT = """\
You are a parser that extracts event research parameters from a natural language message.
Extract the following fields and return them as a JSON object:

- event_type: one of "dinner", "happy_hour", or "workshop" (required)
- city: the city name (required)
- neighborhood: specific area/neighborhood if mentioned
- budget: budget amount if mentioned (keep as string, e.g. "$5,000")
- guest_count: number of guests if mentioned (as integer)
- vibe: atmosphere/vibe keywords if mentioned
- audience: who is attending if mentioned
- requirements: list of must-haves if mentioned
- keywords: any other preference keywords as a list
- date_range: date/timeframe if mentioned
- notes: anything else relevant

If you can't determine the event_type or city, set them to null.
Return ONLY the JSON object, no other text.
"""


class ParseRequest(BaseModel):
    message: str


class ParseResponse(BaseModel):
    status: str
    parsed: dict | None = None
    error: str | None = None


@app.post("/parse", response_model=ParseResponse)
async def parse_message(
    request: ParseRequest,
    authorization: str | None = Header(default=None),
):
    """Parse a natural language message into a structured research request using Claude."""

    _check_auth(authorization)
    config = load_config()

    try:
        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-20250414",
            max_tokens=1000,
            system=PARSE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": request.message}],
        )

        text = response.content[0].text.strip()
        # Extract JSON
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        parsed = json.loads(text)

        # Validate required fields
        if not parsed.get("event_type") or not parsed.get("city"):
            return ParseResponse(
                status="error",
                error="Could not determine event type or city from your message. Please include at least the type of event (dinner, happy hour, or workshop) and the city.",
            )

        return ParseResponse(status="success", parsed=parsed)

    except json.JSONDecodeError:
        return ParseResponse(status="error", error="Failed to parse the message into structured data.")
    except Exception as e:
        return ParseResponse(status="error", error=f"Parse failed: {str(e)}")


class MessageResearchRequest(BaseModel):
    """Send a raw natural language message — we'll parse and research in one call."""
    message: str
    push_to_notion: bool = True
    slack_format: bool = True


@app.post("/research-from-message", response_model=ResearchResponse)
async def research_from_message(
    request: MessageResearchRequest,
    authorization: str | None = Header(default=None),
):
    """One-shot: parse a natural language message and run venue research.

    This is the simplest n8n integration — just forward the Slack message here.
    """

    _check_auth(authorization)

    # Step 1: Parse the message
    parse_result = await parse_message(
        ParseRequest(message=request.message),
        authorization=authorization,
    )

    if parse_result.status != "success" or not parse_result.parsed:
        return ResearchResponse(
            status="error",
            error=parse_result.error or "Could not parse message",
        )

    # Step 2: Run research with parsed data
    parsed = parse_result.parsed
    parsed["push_to_notion"] = request.push_to_notion
    parsed["slack_format"] = request.slack_format

    return await research(
        ResearchRequest(**parsed),
        authorization=authorization,
    )


# ---- Health check endpoint ----

class HealthCheckRequest(BaseModel):
    limit: int = 0  # 0 = check all venues


class HealthCheckResponse(BaseModel):
    status: str
    checked: int = 0
    active: int = 0
    closed: int = 0
    uncertain: int = 0
    results: list[dict] = Field(default_factory=list)
    error: str | None = None


@app.post("/health-check", response_model=HealthCheckResponse)
async def health_check(
    request: HealthCheckRequest = HealthCheckRequest(),
    authorization: str | None = Header(default=None),
):
    """Run health checks on venues in Notion."""

    _check_auth(authorization)
    config = load_config()

    try:
        from event_research.health_check import run_health_checks
        results = run_health_checks(config, limit=request.limit)

        return HealthCheckResponse(
            status="success",
            checked=len(results),
            active=sum(1 for r in results if r.status == "active"),
            closed=sum(1 for r in results if r.status == "closed"),
            uncertain=sum(1 for r in results if r.status in ("uncertain", "error")),
            results=[
                {
                    "venue_name": r.venue_name,
                    "city": r.city,
                    "status": r.status,
                    "details": r.details,
                }
                for r in results
            ],
        )
    except Exception as e:
        return HealthCheckResponse(status="error", error=str(e))


# ---- Outreach endpoint ----

class OutreachRequest(BaseModel):
    """Request to enrich contacts and draft outreach emails."""

    city: str | None = None
    venue_name: str | None = None
    page_id: str | None = None  # specific Notion page ID (for trigger-based outreach)
    project_url: str | None = None  # Notion project page URL or ID (for event details)
    status_filter: list[str] | None = None
    limit: int = 0
    enrich_only: bool = False
    push_to_notion: bool = True
    slack_format: bool = True

    # Event detail overrides (used if no linked Team Project)
    event_type: str | None = None
    budget: str | None = None
    guest_count: int | None = None
    date_range: str | None = None
    vibe: str | None = None
    audience: str | None = None


class OutreachResponse(BaseModel):
    """Response with outreach results."""

    status: str
    total_processed: int = 0
    total_enriched: int = 0
    total_emails_drafted: int = 0
    venues: list[dict] = Field(default_factory=list)
    slack_blocks: list[dict] | None = None
    error: str | None = None


@app.post("/outreach", response_model=OutreachResponse)
async def outreach(
    request: OutreachRequest,
    authorization: str | None = Header(default=None),
):
    """Enrich venue contacts and draft outreach emails."""

    _check_auth(authorization)
    config = load_config()

    try:
        from event_research.notion_sync import (
            get_venues_for_outreach, get_venue_by_page_id,
            get_notion_client, update_venue_outreach,
            get_linked_project_content, fetch_page_content,
        )
        from event_research.outreach_agent import run_outreach_batch
        from event_research.slack_format import format_outreach_for_slack

        # Get venues to process
        if request.page_id:
            # Single venue by page ID (for Notion trigger)
            page = get_venue_by_page_id(config, request.page_id)
            pages = [page] if page else []
        else:
            pages = get_venues_for_outreach(
                config,
                city=request.city,
                venue_name=request.venue_name,
                status_filter=request.status_filter,
            )

        if request.limit > 0:
            pages = pages[:request.limit]

        if not pages:
            return OutreachResponse(
                status="success",
                total_processed=0,
                venues=[],
            )

        # Build event details from request
        event_details = None
        if request.event_type or request.budget or request.guest_count:
            event_details = {
                "event_type": request.event_type or "private event",
                "budget": request.budget,
                "guest_count": request.guest_count,
                "date": request.date_range,
                "vibe": request.vibe,
                "audience": request.audience,
            }

        # Try to get project content — explicit project_url takes priority,
        # then fall back to the first venue's linked Team Project relation
        project_content = None
        if not event_details:
            if request.project_url:
                project_content = fetch_page_content(config, request.project_url)
            else:
                project_content = get_linked_project_content(config, pages[0])

        # Run outreach
        result = run_outreach_batch(
            pages, config,
            event_details=event_details,
            enrich_only=request.enrich_only,
            project_content=project_content,
        )

        # Update Notion if requested
        if request.push_to_notion:
            notion = get_notion_client(config)
            for venue in result.venues:
                if venue.page_id:
                    update_venue_outreach(notion, venue.page_id, venue)

        # Format for Slack if requested
        slack_blocks = None
        if request.slack_format:
            slack_blocks = format_outreach_for_slack(result)

        return OutreachResponse(
            status="success",
            total_processed=result.total_processed,
            total_enriched=result.total_enriched,
            total_emails_drafted=result.total_emails_drafted,
            venues=[v.model_dump() for v in result.venues],
            slack_blocks=slack_blocks,
        )

    except Exception as e:
        return OutreachResponse(
            status="error",
            error=f"Outreach failed: {str(e)}",
        )


def start_server(host: str = "0.0.0.0", port: int = 8000):
    """Start the API server (used by CLI and Dockerfile)."""
    import uvicorn
    uvicorn.run(
        "event_research.api:app",
        host=host,
        port=int(os.getenv("PORT", port)),
        reload=False,
    )


if __name__ == "__main__":
    start_server()
