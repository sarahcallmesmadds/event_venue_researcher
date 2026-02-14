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

## Phase 2: n8n + Slack Integration ← IN PROGRESS
Wire the agent into Slack via n8n so you can interact conversationally.

- [x] FastAPI wrapper (POST /research, GET /health)
- [x] Slack Block Kit message formatter
- [x] n8n workflow export (Slack trigger → parse → agent API → Slack response)
- [x] Railway deploy config (Dockerfile + railway.json)
- [ ] **SETUP REQUIRED — see below**

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
