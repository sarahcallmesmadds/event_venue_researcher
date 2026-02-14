# Hosted Event Research Agent — Build Plan

## Phase 1: Core Python Agent + Notion DB ✅
Get the research agent working end-to-end: give it event criteria, it returns venue recommendations, stores them in Notion.

- [x] Set up Python project structure (pyproject.toml, src/, config)
- [x] Create Notion "Event Venue Research" database with schema
- [x] Build the core research agent (Claude API + web search tool use)
- [x] Build event-type templates (dinner, happy hour, workshop)
- [x] Build Notion integration (push results, check existing, archive stale)
- [x] Config file for API keys, Notion DB ID, defaults
- [x] Test end-to-end: CLI input → research → Notion output

## Phase 2: n8n + Slack Integration ✅ (code complete, setup at new company)
Wire the agent into Slack via n8n so you can interact conversationally.

- [x] FastAPI wrapper (POST /research, GET /health)
- [x] Slack Block Kit message formatter
- [x] n8n workflow export (Slack trigger → parse → agent API → Slack response)
- [x] Railway deploy config (Dockerfile + railway.json)
- [ ] **SETUP REQUIRED at new company — see below**

### Phase 2 Setup Steps

#### 1. Deploy to Railway
1. Push this branch to GitHub
2. Go to [railway.com](https://railway.com) → New Project → Deploy from GitHub repo
3. Set these env vars in Railway:
   - `ANTHROPIC_API_KEY` — your Anthropic API key
   - `NOTION_API_KEY` — your Notion integration key
   - `NOTION_DATABASE_ID` — `4210f38f614848c4a957bd5b2a8f2f80`
   - `API_SECRET` — any random string (used to auth n8n → agent calls)
4. Railway will build from the Dockerfile and give you a URL like `https://your-app.up.railway.app`
5. Test: `curl https://your-app.up.railway.app/health`

#### 2. Create Slack Bot
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create New App
2. Add Bot Token Scopes: `chat:write`, `im:history`, `im:read`, `im:write`
3. Install to workspace → copy the Bot OAuth Token
4. Enable Event Subscriptions → subscribe to `message.im`

#### 3. Import n8n Workflow
1. In n8n cloud, go to Workflows → Import from File
2. Import `n8n/event_research_workflow.json`
3. Set n8n environment variables:
   - `RESEARCH_AGENT_URL` — your Railway URL (e.g. `https://your-app.up.railway.app`)
   - `API_SECRET` — same secret you set in Railway
4. Connect the Slack nodes to your Slack bot credentials
5. Activate the workflow

#### 4. Test It
DM the Slack bot something like:
> I need to host an intimate dinner for 20 CMOs in the West Village, NYC. Budget is $5k. Looking for upscale vibes with a private dining room.

The bot will acknowledge, research (1-2 min), and post venue results back.

## Phase 3: Venue Health Checks + Memory ✅
Make the Notion DB self-maintaining and the agent smarter over time.

- [x] Venue health check agent (web search to verify venues still active)
- [x] Auto-archive closed venues, update corrected contact info
- [x] Agent checks Notion first before searching externally (reuses existing venues)
- [x] `--new-only` flag to skip Notion lookup and only return fresh web results
- [x] Health check CLI command and API endpoint (`/health-check`)
- [ ] **SETUP REQUIRED at new company — see below**

### Phase 3 Setup Steps

#### Notion "Team Projects" Relation + Formula
When you create the **Team Projects** database at your new company, come back and do this:

1. **Add a Relation property** to the "Event Venue Research" DB:
   - Property name: `Team Projects`
   - Type: Relation
   - Related database: your Team Projects DB
   - This links venues to the events/projects they were used for

2. **Add a Formula property** to the "Event Venue Research" DB:
   - Property name: `Has Successful Event`
   - Type: Formula
   - Formula: `if(length(filter(prop("Team Projects"), current.prop("Status") == "Done" and current.prop("Status") != "Canceled")) > 0, true, false)`
   - This returns `true` if any linked Team Project has status "Done" (and not "Canceled")
   - Adjust the property names in the formula to match your actual Team Projects DB schema

> **Note:** These can't be created programmatically until the Team Projects DB exists. The Notion API requires the target database ID when creating a Relation property.

#### Triggering Health Checks
- **Manual (CLI):** `event-research health-check --limit 10`
- **Manual (API):** `POST /health-check` on your Railway deployment
- **From Notion:** Add a button in Notion that calls the Railway `/health-check` endpoint
- **Scheduled:** Set up an n8n workflow with a Cron trigger to call `/health-check` on a schedule (e.g., weekly)

## Phase 4: Outreach Agent Handoff
Prep for the venue outreach agent you mentioned.

- [ ] Standardized venue data format for outreach agent
- [ ] Flag "ready for outreach" in Notion
- [ ] Outreach agent scaffold
