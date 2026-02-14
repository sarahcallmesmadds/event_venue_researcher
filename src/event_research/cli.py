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


if __name__ == "__main__":
    main()
