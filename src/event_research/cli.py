"""CLI entry point for testing the research agent."""

from __future__ import annotations

import argparse
import json
import sys

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from event_research.config import load_config
from event_research.models import EventBrief, EventType, ResearchResult
from event_research.agent import run_research
from event_research.notion_sync import push_results_to_notion

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Event Venue Research Agent")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # --- serve command ---
    serve_parser = subparsers.add_parser("serve", help="Start the API server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    # --- research command ---
    research_parser = subparsers.add_parser("research", help="Research venues for an event")
    research_parser.add_argument("--type", required=True, choices=["dinner", "happy_hour", "workshop"], help="Event type")
    research_parser.add_argument("--city", required=True, help="City to search in")
    research_parser.add_argument("--neighborhood", help="Specific neighborhood or area")
    research_parser.add_argument("--budget", help="Budget (e.g. '$5,000', 'under $200pp')")
    research_parser.add_argument("--guests", type=int, help="Number of guests")
    research_parser.add_argument("--vibe", help="Vibe/atmosphere keywords")
    research_parser.add_argument("--audience", help="Who is attending (e.g. 'CMOs', 'engineers')")
    research_parser.add_argument("--requirements", nargs="*", help="Must-have requirements")
    research_parser.add_argument("--keywords", nargs="*", help="Keywords/preferences")
    research_parser.add_argument("--date", help="Target date range")
    research_parser.add_argument("--notes", help="Additional notes")
    research_parser.add_argument("--no-notion", action="store_true", help="Skip pushing to Notion")
    research_parser.add_argument("--new-only", action="store_true", help="Skip Notion lookup, only return new web search results")
    research_parser.add_argument("--json-out", help="Save raw JSON results to file")

    # --- health-check command ---
    health_parser = subparsers.add_parser("health-check", help="Verify venues in Notion are still active")
    health_parser.add_argument("--limit", type=int, default=0, help="Max venues to check (0 = all)")

    # --- outreach command ---
    outreach_parser = subparsers.add_parser("outreach", help="Enrich venue contacts and draft outreach emails")
    outreach_parser.add_argument("--city", help="Filter venues by city")
    outreach_parser.add_argument("--venue", help="Filter by venue name (partial match)")
    outreach_parser.add_argument("--status", help="Filter by status (default: New + Ready for Outreach)")
    outreach_parser.add_argument("--limit", type=int, default=0, help="Max venues to process (0 = all matching)")
    outreach_parser.add_argument("--enrich-only", action="store_true", help="Only enrich contacts, skip email drafting")
    outreach_parser.add_argument("--no-notion", action="store_true", help="Skip updating Notion")
    outreach_parser.add_argument("--json-out", help="Save results to JSON file")
    # Event detail overrides for email drafting (used if no linked Team Project)
    outreach_parser.add_argument("--type", choices=["dinner", "happy_hour", "workshop"], help="Event type (for email drafting)")
    outreach_parser.add_argument("--budget", help="Budget (for email drafting)")
    outreach_parser.add_argument("--guests", type=int, help="Guest count (for email drafting)")
    outreach_parser.add_argument("--date", help="Target date (for email drafting)")
    outreach_parser.add_argument("--vibe", help="Vibe (for email drafting)")
    outreach_parser.add_argument("--audience", help="Audience (for email drafting)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "serve":
        from event_research.api import start_server
        start_server(host=args.host, port=args.port)
    elif args.command == "research":
        _handle_research(args)
    elif args.command == "health-check":
        _handle_health_check(args)
    elif args.command == "outreach":
        _handle_outreach(args)


def _handle_research(args):
    config = load_config()

    # Validate config
    missing = config.validate_keys()
    notion_missing = "NOTION_DATABASE_ID" in missing or "NOTION_API_KEY" in missing
    if "ANTHROPIC_API_KEY" in missing:
        console.print("[red]❌ ANTHROPIC_API_KEY is required. Set it in .env[/red]")
        sys.exit(1)
    if notion_missing and not args.no_notion:
        console.print("[yellow]⚠️  Notion keys missing — running with --no-notion[/yellow]")
        args.no_notion = True

    # Build the brief
    brief = EventBrief(
        event_type=EventType(args.type),
        city=args.city,
        neighborhood=args.neighborhood,
        budget=args.budget,
        guest_count=args.guests,
        vibe=args.vibe,
        audience=args.audience,
        requirements=args.requirements or [],
        keywords=args.keywords or [],
        date_range=args.date,
        notes=args.notes,
    )

    # Show the brief
    console.print(Panel(
        f"[bold]Event Type:[/bold] {brief.event_type.value}\n"
        f"[bold]City:[/bold] {brief.city}\n"
        f"[bold]Neighborhood:[/bold] {brief.neighborhood or 'Any'}\n"
        f"[bold]Budget:[/bold] {brief.budget or 'Not specified'}\n"
        f"[bold]Guests:[/bold] {brief.guest_count or 'Not specified'}\n"
        f"[bold]Vibe:[/bold] {brief.vibe or 'Not specified'}\n"
        f"[bold]Audience:[/bold] {brief.audience or 'Not specified'}",
        title="📋 Event Brief",
        border_style="blue",
    ))

    # Run research
    result = run_research(brief, config, skip_notion_lookup=args.new_only)

    # Display results
    _display_results(result)

    # Save JSON if requested
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(result.model_dump(), f, indent=2, default=str)
        console.print(f"\n💾 Results saved to {args.json_out}")

    # Push to Notion
    if not args.no_notion and result.venues:
        console.print("\n📤 Pushing to Notion...")
        urls = push_results_to_notion(result, config)
        console.print(f"   {len(urls)} venue(s) added to Notion")

    if not result.venues:
        console.print("\n[yellow]No venues found. Try broadening your search criteria.[/yellow]")


def _display_results(result: ResearchResult):
    """Pretty-print venue results to the console."""

    if result.research_notes:
        console.print(Panel(result.research_notes, title="🗒️  Research Notes", border_style="dim"))

    if not result.venues:
        return

    console.print(f"\n[bold green]Found {len(result.venues)} venue(s):[/bold green]\n")

    for i, v in enumerate(result.venues, 1):
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="bold cyan", width=16)
        table.add_column("Value")

        table.add_row("Address", v.address)
        table.add_row("Type", v.venue_type)
        if v.website:
            table.add_row("Website", v.website)
        if v.phone:
            table.add_row("Phone", v.phone)
        if v.email:
            table.add_row("Email", v.email)
        if v.contact_name:
            table.add_row("Contact", v.contact_name)
        if v.price_range:
            table.add_row("Price Range", v.price_range)
        if v.estimated_cost:
            table.add_row("Est. Cost", v.estimated_cost)
        if v.capacity_min or v.capacity_max:
            cap = f"{v.capacity_min or '?'} – {v.capacity_max or '?'} guests"
            table.add_row("Capacity", cap)
        if v.private_space is not None:
            table.add_row("Private Space", "✅" if v.private_space else "❌")
        if v.av_available is not None:
            table.add_row("AV Available", "✅" if v.av_available else "❌")
        if v.cuisine_or_style:
            table.add_row("Cuisine/Style", v.cuisine_or_style)
        if v.highlights:
            table.add_row("Why It Fits", v.highlights)
        table.add_row("Confidence", f"[{'green' if v.confidence == 'high' else 'yellow' if v.confidence == 'medium' else 'red'}]{v.confidence}[/]")

        console.print(Panel(table, title=f"[bold]{i}. {v.name}[/bold]", border_style="green"))


def _handle_health_check(args):
    config = load_config()

    missing = config.validate_keys()
    if "ANTHROPIC_API_KEY" in missing:
        console.print("[red]❌ ANTHROPIC_API_KEY is required. Set it in .env[/red]")
        sys.exit(1)
    if "NOTION_API_KEY" in missing or "NOTION_DATABASE_ID" in missing:
        console.print("[red]❌ Notion keys are required for health checks. Set them in .env[/red]")
        sys.exit(1)

    from event_research.health_check import run_health_checks
    results = run_health_checks(config, limit=args.limit)

    if not results:
        console.print("\n[yellow]No venues to check.[/yellow]")


def _handle_outreach(args):
    config = load_config()

    # Validate config
    missing = config.validate_keys()
    if "ANTHROPIC_API_KEY" in missing:
        console.print("[red]❌ ANTHROPIC_API_KEY is required. Set it in .env[/red]")
        sys.exit(1)
    if "NOTION_API_KEY" in missing or "NOTION_DATABASE_ID" in missing:
        console.print("[red]❌ Notion keys are required for outreach. Set them in .env[/red]")
        sys.exit(1)

    from event_research.notion_sync import (
        get_venues_for_outreach, get_notion_client, update_venue_outreach,
        get_linked_project_content,
    )
    from event_research.outreach_agent import run_outreach_batch

    # Build status filter
    status_filter = None
    if args.status:
        status_filter = [s.strip() for s in args.status.split(",")]

    # Query Notion for matching venues
    pages = get_venues_for_outreach(
        config,
        city=args.city,
        venue_name=args.venue,
        status_filter=status_filter,
    )

    if args.limit > 0:
        pages = pages[:args.limit]

    if not pages:
        console.print("\n[yellow]No matching venues found in Notion.[/yellow]")
        if args.city:
            console.print(f"   City filter: {args.city}")
        if args.venue:
            console.print(f"   Venue filter: {args.venue}")
        return

    console.print(f"\n[bold]Found {len(pages)} venue(s) to process[/bold]")

    # Build event details from CLI args (if provided)
    event_details = None
    if args.type or args.budget or args.guests or args.date:
        event_details = {
            "event_type": args.type or "private event",
            "budget": args.budget,
            "guest_count": args.guests,
            "date": args.date,
            "vibe": args.vibe,
            "audience": args.audience,
        }

    # Try to get project content from the first venue's linked Team Project
    project_content = None
    if not event_details:
        project_content = get_linked_project_content(config, pages[0])
        if project_content:
            console.print("[dim]Found linked Team Project — extracting event details...[/dim]")

    # Run outreach
    result = run_outreach_batch(
        pages, config,
        event_details=event_details,
        enrich_only=args.enrich_only,
        project_content=project_content,
    )

    # Display results
    _display_outreach_results(result)

    # Save JSON if requested
    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(result.model_dump(), f, indent=2, default=str)
        console.print(f"\n💾 Results saved to {args.json_out}")

    # Update Notion
    if not args.no_notion:
        console.print("\n📤 Updating Notion...")
        notion = get_notion_client(config)
        updated = 0
        for venue in result.venues:
            if venue.page_id:
                update_venue_outreach(notion, venue.page_id, venue)
                updated += 1
        console.print(f"   {updated} venue(s) updated in Notion")


def _display_outreach_results(result):
    """Pretty-print outreach results to the console."""
    from event_research.models import OutreachResult

    if not result.venues:
        return

    console.print(f"\n[bold green]Outreach results for {len(result.venues)} venue(s):[/bold green]\n")

    for i, v in enumerate(result.venues, 1):
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Field", style="bold cyan", width=18)
        table.add_column("Value")

        if v.address:
            table.add_row("Address", v.address)
        if v.website:
            table.add_row("Website", v.website)
        if v.price_range:
            table.add_row("Price Range", v.price_range)

        # Contact info — show original vs enriched
        table.add_row("", "")  # spacer
        table.add_row("[bold]Contact Info[/bold]", "")

        contact = v.enriched_contact_name or v.original_contact_name
        if contact:
            title_str = f" ({v.enriched_contact_title})" if v.enriched_contact_title else ""
            new_tag = " [green]NEW[/green]" if v.enriched_contact_name and v.enriched_contact_name != v.original_contact_name else ""
            table.add_row("Contact", f"{contact}{title_str}{new_tag}")

        email = v.enriched_email or v.original_email
        if email:
            new_tag = " [green]NEW[/green]" if v.enriched_email and v.enriched_email != v.original_email else ""
            table.add_row("Email", f"{email}{new_tag}")

        phone = v.enriched_phone or v.original_phone
        if phone:
            new_tag = " [green]NEW[/green]" if v.enriched_phone and v.enriched_phone != v.original_phone else ""
            table.add_row("Phone", f"{phone}{new_tag}")

        if v.private_events_url:
            table.add_row("Events Page", v.private_events_url)
        if v.booking_form_url:
            table.add_row("Booking Form", v.booking_form_url)

        confidence_color = {"high": "green", "medium": "yellow", "low": "red"}.get(v.enrichment_confidence, "dim")
        table.add_row("Confidence", f"[{confidence_color}]{v.enrichment_confidence}[/]")

        if v.enrichment_notes:
            table.add_row("Notes", v.enrichment_notes[:200])

        console.print(Panel(table, title=f"[bold]{i}. {v.name}[/bold] — {v.city}", border_style="cyan"))

        # Show email draft if available
        if v.email_subject and v.email_body:
            email_text = f"[bold]Subject:[/bold] {v.email_subject}\n\n{v.email_body}"
            console.print(Panel(email_text, title="✉️  Draft Email", border_style="dim", padding=(1, 2)))

        console.print("")  # spacer


if __name__ == "__main__":
    main()
