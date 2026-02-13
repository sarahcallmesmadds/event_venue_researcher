# Hosted Event Research Agent — Build Plan

## Phase 1: Core Python Agent + Notion DB (TODAY)
Get the research agent working end-to-end: give it event criteria, it returns venue recommendations, stores them in Notion.

- [ ] Set up Python project structure (pyproject.toml, src/, config)
- [ ] Create Notion "Event Venue Research" database with schema
- [ ] Build the core research agent (Claude API + web search tool use)
- [ ] Build event-type templates (dinner, happy hour, workshop)
- [ ] Build Notion integration (push results, check existing, archive stale)
- [ ] Config file for API keys, Notion DB ID, defaults
- [ ] Test end-to-end: CLI input → research → Notion output

## Phase 2: n8n + Slack Integration
Wire the agent into Slack via n8n so you can interact conversationally.

- [ ] n8n workflow: Slack trigger → call Python agent → post results back
- [ ] Intake flow (smart follow-up questions based on event type)
- [ ] Async research with status updates in Slack thread

## Phase 3: Venue Health Checks + Memory
Make the Notion DB self-maintaining and the agent smarter over time.

- [ ] Scheduled venue validation (still in business? updated info?)
- [ ] Auto-archive dead venues
- [ ] Agent checks Notion first before searching externally
- [ ] Learning from past research (what worked, user feedback)

## Phase 4: Outreach Agent Handoff
Prep for the venue outreach agent you mentioned.

- [ ] Standardized venue data format for outreach agent
- [ ] Flag "ready for outreach" in Notion
- [ ] Outreach agent scaffold
