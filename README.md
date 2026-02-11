<p align="center">
  <img src=".github/assets/rainbow-logo.svg" alt="Ultraworker" width="500" />
</p>

<p align="center">
  <strong>AI-Powered Slack Agent with Human-in-the-Loop Workflow Orchestration</strong>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT" /></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python 3.11+" /></a>
  <a href="https://github.com/anthropics/claude-code"><img src="https://img.shields.io/badge/Claude_Code-Compatible-orange.svg" alt="Claude Code" /></a>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#what-is-ultraworker">About</a> •
  <a href="#features">Features</a> •
  <a href="#skills">Skills</a> •
  <a href="#configuration">Configuration</a>
</p>

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- [Claude Code CLI](https://github.com/anthropics/claude-code)
- Node.js 18+ (for MCP servers)

### Installation

```bash
# Clone the repository
git clone https://github.com/sionic-ai/ultraworker.git
cd ultraworker

# Install dependencies
uv sync

# Run the setup wizard (interactive TUI)
uv run ultrawork setup
```

The setup wizard guides you through:
1. Claude Code authentication
2. Slack token configuration
3. Trigger mode selection (mention vs. keyword)
4. MCP server installation
5. Dashboard launch

### Manual Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit with your tokens
# SLACK_TOKEN=xoxc-your-personal-token
# SLACK_COOKIE=xoxd-your-cookie
# SLACK_BOT_TOKEN=xoxb-your-bot-token (optional)

# Copy MCP configuration template
cp .mcp.json.example .mcp.json
# Edit with your actual tokens
```

### Running

```bash
# Start the polling daemon (monitors Slack mentions)
uv run python -m ultrawork.slack.sdk_poller --agentic

# Start the dashboard (optional)
uv run ultrawork dashboard
```

---

## What is Ultraworker?

Ultraworker transforms Slack mentions into structured tasks through an AI-powered 4-stage approval workflow. When someone mentions your bot, it automatically:

1. **Explores Context** - Searches related conversations, decisions, and history
2. **Creates TODOs** - Generates actionable task lists with effort estimates
3. **Writes Tech Specs** - Produces detailed implementation plans
4. **Generates Reports** - Summarizes completed work with verification checklists

Each stage requires human approval before proceeding, ensuring oversight while maximizing automation.

```
Slack Mention → Context Exploration → TODO Creation → [Approval 1]
                                                           ↓
                       Tech Spec Writing ← ─ ─ ─ ─ ─ ─ ─ ─ ┘
                             ↓
                      [Approval 2] → Code Implementation → [Approval 3]
                                                                 ↓
                             Final Report ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
                                  ↓
                           [Approval 4] → Done
```

---

## Features

| Feature | Description |
|---------|-------------|
| **Slack Integration** | Monitors mentions across channels and DMs with real-time polling |
| **Context Exploration** | Recursively searches related threads, decisions, and discussions |
| **4-Stage Workflow** | TODO → Tech Spec → Code → Report with human approval gates |
| **Claude Code Skills** | Modular slash commands for each workflow step |
| **Real-time Dashboard** | Web UI showing session topology, tool calls, and event streams |
| **Session Management** | Track multiple concurrent agent sessions per thread |
| **MCP Tool Support** | Integrates with Slack MCP, Playwright, Context7, and custom servers |

---

## Skills

Skills are Claude Code slash commands that handle specific workflow steps.

| Skill | Description |
|-------|-------------|
| `/sync-slack` | Synchronize channel and user registry |
| `/explore-context` | Explore thread/keyword context |
| `/create-todo` | Generate TODO list from exploration |
| `/write-spec` | Write technical specification |
| `/approve` | Approve current workflow stage |
| `/reject` | Request revisions with feedback |
| `/report` | Generate final completion report |

### Usage Examples

```bash
/sync-slack
/explore-context C0123456789-1706500000.000000
/create-todo EXP-2026-0129-001
/approve TASK-2026-0129-001
/write-spec TASK-2026-0129-001
/report TASK-2026-0129-001
```

---

## Configuration

### ultrawork.yaml

```yaml
slack:
  bot_user_id: U0XXXXXXXXX
  trigger_pattern: ""
  default_channel: ""

polling:
  enabled: true
  poll_interval_seconds: 60

workflow:
  default_workflow_type: full
  require_tech_spec_for_code: true
```

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SLACK_TOKEN` | Personal token (xoxc-...) | Yes* |
| `SLACK_COOKIE` | Cookie (xoxd-...) for xoxc tokens | With xoxc |
| `SLACK_BOT_TOKEN` | Bot token (xoxb-...) | Optional |

*Either `SLACK_TOKEN` or `SLACK_BOT_TOKEN` is required.

---

## MCP Server Setup

```bash
# Slack (Personal Token)
claude mcp add slack -- npx -y @jtalk22/slack-mcp

# Slack Bot
claude mcp add slack-bot -- npx -y slack-bot-mcp

# Playwright (Browser automation)
claude mcp add playwright -- npx -y @playwright/mcp@latest

# Context7 (Library docs)
claude mcp add context7 -- npx -y @upstash/context7-mcp@latest
```

---

## CLI Commands

```bash
uv run ultrawork --help              # Show available commands
uv run ultrawork setup               # Run setup wizard
uv run ultrawork dashboard           # Start web dashboard
uv run ultrawork slack:sync          # Sync channels/users
uv run ultrawork task:list           # List all tasks
```

---

## Development

```bash
make dev        # Install dev dependencies
make format     # Format code
make check      # Run linters and type checks
make test       # Run tests
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT License - see [LICENSE](LICENSE) for details.
