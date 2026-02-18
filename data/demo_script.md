# Ultraworker -- 2-Minute Demo Video Script

**Event:** Claude Code Birthday Party & Showcase
**Duration:** 2 minutes (120 seconds)
**Presenter:** [Speaker Name]
**Format:** Screen recording with voiceover narration

---

## [0:00 -- 0:10] OPENING: The Hook

**VISUAL:** Slack notification sound. Screen shows a busy Slack workspace with messages flying in. A mention appears: `@ultraworker Can you refactor our authentication module to support OAuth2?`

**NARRATION:**

> "Every day, your team drops requests in Slack and hopes someone picks them up. What if an AI agent could catch every mention, understand the full context, plan the work, write specs, implement code, and report back -- all while keeping a human in the loop at every step?"

---

## [0:10 -- 0:30] WHAT IS ULTRAWORKER: Problem and Solution

**VISUAL:** Animated workflow diagram fades in, showing the four-stage pipeline:

```
Slack Mention --> Context Exploration --> TODO --> [Approval]
                                                      |
                    Tech Spec <------------------------+
                       |
                  [Approval] --> Code Implementation --> [Approval]
                                                            |
                       Final Report <-----------------------+
                            |
                      [Approval] --> Done
```

**NARRATION:**

> "This is Ultraworker -- an AI-powered Slack agent built entirely with Claude Code. It transforms Slack mentions into fully tracked, multi-stage workflows with four human approval gates. No task slips through the cracks. No work happens without your sign-off."

> "It connects to Slack through MCP tools, runs Claude Code skills as modular slash commands, and gives you a real-time dashboard to watch everything unfold."

---

## [0:30 -- 1:30] LIVE DEMO WALKTHROUGH: The Workflow in Action

### Act 1: The Mention [0:30 -- 0:42]

**VISUAL:** Slack channel. Someone types: `@ultraworker We need to add rate limiting to the API gateway. Users are reporting 429 errors under load.`

The bot reacts with a eyes emoji within seconds.

**NARRATION:**

> "Someone mentions Ultraworker in Slack. The polling daemon detects it instantly and reacts with an eyes emoji -- the team knows work has begun."

> "Behind the scenes, a new agent session spins up. Claude Code receives the context and starts the first skill: `/explore-context`."

---

### Act 2: Context Exploration [0:42 -- 0:54]

**VISUAL:** Split screen. Left: Slack showing the bot's reply with a context summary. Right: the data/explorations/ directory with a newly generated EXP-2026-0219-001.md file.

**NARRATION:**

> "The agent searches related Slack threads, checks channel history memory for past discussions about rate limiting, and produces a structured exploration document. It finds three related threads from the past month -- including a decision to use token-bucket algorithms."

> "This is not just keyword search. It builds a relevance-scored context graph across your workspace."

---

### Act 3: TODO Creation and First Approval [0:54 -- 1:06]

**VISUAL:** Slack message from Ultraworker showing a formatted TODO list with effort estimates. A team lead reacts with a thumbs-up emoji.

**NARRATION:**

> "From the exploration, it generates a concrete TODO list with effort estimates and posts it back to the thread for approval. The `/create-todo` skill handles this automatically."

> "A team lead reviews and approves with a thumbs-up. Stage one -- cleared."

---

### Act 4: Tech Spec, Code, and Report [1:06 -- 1:22]

**VISUAL:** Quick montage:
1. A tech spec document appearing in `data/specs/` with sections for Problem Statement, Implementation Details, and Testing Strategy.
2. Terminal showing Claude Code running, writing actual Python code with rate limiting logic.
3. Final report posted to Slack with a verification checklist -- all items checked.

**NARRATION:**

> "Now it writes a full tech spec -- problem statement, implementation plan, testing strategy. After approval, Claude Code implements the actual code changes. After another approval, it generates a final report with before-and-after comparisons and test results."

> "Four stages. Four human approvals. Zero tasks forgotten."

---

### Act 5: Dashboard Reveal [1:22 -- 1:30]

**VISUAL:** Browser opens to `localhost:7878`. The dashboard shows:
- Session topology with workflow nodes (trigger, skills, approval gates) connected by edges
- Real-time event stream showing tool calls scrolling in via SSE
- Session status cards with role transitions (RESPONDER to PLANNER to SPEC_WRITER to IMPLEMENTER to REPORTER)

**NARRATION:**

> "And the whole time, this dashboard is streaming every event in real time -- session topology, tool calls, skill executions, approval states. You see exactly what the agent is doing and why."

---

## [1:30 -- 1:50] ARCHITECTURE AND TECHNICAL HIGHLIGHTS

**VISUAL:** Terminal showing the project structure and key commands:
```
uv run ultrawork start          # Launches poller + dashboard
/sync-slack                     # 11 Claude Code skills
/explore-context                # MCP: Slack, Playwright, Context7
/manage-cronjob                 # Scheduled monitoring
```

**NARRATION:**

> "Under the hood: eleven Claude Code slash commands as modular skills. MCP tool integration with Slack, Playwright for browser automation, and Context7 for library docs. A cron scheduler for recurring tasks. Channel history memory so the agent understands your project terminology."

> "It is built with Python, Pydantic models, a custom HTTP dashboard with SSE streaming, and YAML-based persistence. The entire system bootstraps with a single command: `uv run ultrawork start`."

---

## [1:50 -- 2:00] THE META MOMENT: Closing

**VISUAL:** Terminal showing a Slack mention that reads: `@ultraworker Deploy yourself for the Claude Code Birthday demo.` The agent reacts with eyes, starts processing, and a final checkmark appears.

**NARRATION:**

> "And here is the part that still gets me. The agent you just watched? It was asked to prepare its own demo for this very presentation. It explored its own codebase, wrote its own deployment spec, and reported back when it was done."

> "This is Ultraworker. Built with Claude Code. Deployed by Claude Code. Happy birthday."

**VISUAL:** Logo and repository URL fade in:
```
github.com/DolbonIn/ultraworker
```

---

## Production Notes

### Screen Recording Checklist

- [ ] Slack workspace with realistic channel names and messages preloaded
- [ ] Ultraworker polling daemon running (`uv run ultrawork start`)
- [ ] Dashboard open at `localhost:7878` with at least one active session
- [ ] Terminal with clean prompt for command demonstrations
- [ ] Pre-staged exploration, task, and spec files in `data/` for smooth cuts

### Timing Breakdown

| Section | Duration | Cumulative |
|---------|----------|------------|
| Opening hook | 10s | 0:10 |
| What is Ultraworker | 20s | 0:30 |
| Live demo walkthrough | 60s | 1:30 |
| Architecture highlights | 20s | 1:50 |
| Meta moment and close | 10s | 2:00 |

### Key Visual Assets Needed

1. Slack workspace with the bot configured and responding
2. Dashboard with a completed workflow session showing all node states
3. Terminal showing `uv run ultrawork start` output
4. The exploration, TODO, spec, and report documents in the data directory
5. Git log showing commits made by the agent during code implementation

### Audio Notes

- Background music: Subtle, upbeat electronic (fade under narration)
- Slack notification sound at 0:00 for the hook
- Brief keyboard typing sounds during the code implementation montage
- Clean cut to silence before the meta moment for dramatic effect

### Narration Style

- Confident but conversational, not salesy
- Pace: ~150 words per minute (standard for tech demos)
- Emphasis on "human in the loop" and "four approval gates" -- these are differentiators
- The meta moment should land with a slight pause before "Happy birthday"
