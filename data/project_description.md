# Ultraworker - Claude Code Birthday Party & Showcase Submission

## Short Pitch (Title/Headline)

Ultraworker: An open-source AI Slack agent that turns mentions into fully executed tasks through a 4-stage human-in-the-loop approval workflow -- built entirely with Claude Code, orchestrated by Claude Code, and capable of deploying itself with Claude Code.

## Detailed Description

Ultraworker is a production-grade workflow orchestration system that bridges the gap between AI autonomy and human oversight. When someone mentions the bot in Slack, it kicks off an automated pipeline: exploring context across related conversations, generating structured TODOs with effort estimates, writing detailed technical specifications, implementing code changes, and producing final reports -- all while requiring human approval at each stage before proceeding. The entire system was built from scratch using Claude Code, and Claude Code itself serves as the runtime engine that executes each workflow step through a modular skill system (slash commands like `/explore-context`, `/write-spec`, `/approve`, and `/report`).

What makes Ultraworker unique is that it treats Claude Code not just as a development tool but as an operating system for AI-driven work. The project ships with a real-time web dashboard that visualizes session topology, tool calls, and event streams via SSE. It includes a channel history memory system that stores quarterly conversation summaries so the agent maintains long-term organizational context. A built-in cron scheduler automates recurring monitoring tasks. The agent manages its own sessions with role transitions (Responder, Planner, Spec Writer, Implementer, Reporter) and tracks workflows through persistent YAML-based state. It integrates with multiple MCP servers (Slack, Playwright, Context7) and gracefully handles fallback strategies when tools fail. Perhaps most remarkably, Ultraworker can deploy and configure itself -- making it a truly self-sustaining Claude Code native application.

## Key Technical Highlights

- **4-Stage Approval Workflow**: Slack Mention -> Context Exploration -> TODO Creation -> [Approval] -> Tech Spec -> [Approval] -> Code Implementation -> [Approval] -> Final Report -> [Approval] -> Done. Every stage gates on human approval, ensuring oversight without sacrificing automation.

- **Built Entirely with Claude Code**: From initial architecture to every feature, bugfix, and refactoring -- the entire codebase was developed using Claude Code as the primary development environment.

- **Claude Code as Runtime**: The system uses Claude Code's skill system (11 custom slash commands) as its execution engine, making Claude Code both the builder and the operator.

- **Real-Time Web Dashboard**: A local HTTP dashboard with SSE streaming that visualizes active sessions, workflow graphs, tool call traces, and event timelines -- giving full transparency into what the agent is doing and why.

- **Channel History Memory**: Stores quarterly conversation summaries from Slack channels with terminology dictionaries, enabling the agent to understand internal jargon, past decisions, and organizational context across sessions.

- **Multi-MCP Integration**: Orchestrates across Slack MCP (personal and bot tokens with automatic fallback), Playwright MCP (browser automation for testing), and Context7 MCP (library documentation lookup).

- **Cron Job Scheduler**: Built-in scheduling system for recurring tasks like thread reaction monitoring, mention scanning, and pending task reminders -- turning the agent into an always-on team member.

- **Session & State Management**: Tracks multiple concurrent agent sessions with role-based transitions, persistent YAML state, context memory per session, and a full event/interaction log.

- **Self-Deploying**: Ultraworker includes an interactive TUI setup wizard and can configure its own MCP servers, environment variables, and deployment -- it literally sets itself up.

- **Open Source**: MIT licensed, available at github.com/sionic-ai/ultraworker. Python 3.11+, built with Pydantic, Typer, Rich, Slack SDK, Anthropic SDK, and Playwright.

## Links

- GitHub: https://github.com/sionic-ai/ultraworker
- License: MIT
