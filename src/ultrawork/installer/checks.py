"""System checks and validation for Ultraworker setup."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    ok: bool
    message: str
    detail: str = ""


SETUP_STATE_FILE = ".ultrawork-setup-state.json"


@dataclass
class SetupState:
    """Tracks the entire setup wizard state."""

    project_dir: Path = field(default_factory=Path.cwd)
    # Step 0: Language selection
    language: str = "en"  # Language code (en, ko, ja, zh, es, fr, de, pt)
    # Step 1: Claude Code
    claude_logged_in: bool = False
    claude_version: str = ""
    # Step 2: Slack tokens
    slack_bot_token: str = ""
    slack_personal_token: str = ""
    slack_personal_cookie: str = ""
    slack_token_type: str = ""  # "bot", "personal", "both"
    # Step 3: Basic settings
    bot_user_id: str = ""
    trigger_mode: str = "mention"  # "mention" or "keyword"
    custom_keyword: str = ""
    permission_mode: str = "default"  # "default" or "dangerously-skip-permissions"
    # Step 4: MCPs
    mcps_to_install: list[str] = field(default_factory=list)
    # Step 5: Channels
    channels: list[dict] = field(default_factory=list)
    # Step 7: Dashboard
    dashboard_port: int = 7878
    # Progress tracking
    last_completed_step: int = 0

    def get_env_vars(self) -> dict[str, str]:
        env = {}
        if self.slack_bot_token:
            env["SLACK_BOT_TOKEN"] = self.slack_bot_token
        if self.slack_personal_token:
            env["SLACK_TOKEN"] = self.slack_personal_token
        if self.slack_personal_cookie:
            env["SLACK_COOKIE"] = self.slack_personal_cookie
        return env

    def save(self) -> None:
        """Save state to file for recovery."""
        state_file = self.project_dir / SETUP_STATE_FILE
        data = {
            "language": self.language,
            "slack_bot_token": self.slack_bot_token,
            "slack_personal_token": self.slack_personal_token,
            "slack_personal_cookie": self.slack_personal_cookie,
            "slack_token_type": self.slack_token_type,
            "bot_user_id": self.bot_user_id,
            "trigger_mode": self.trigger_mode,
            "custom_keyword": self.custom_keyword,
            "permission_mode": self.permission_mode,
            "mcps_to_install": self.mcps_to_install,
            "channels": self.channels,
            "dashboard_port": self.dashboard_port,
            "last_completed_step": self.last_completed_step,
        }
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, project_dir: Path | None = None) -> "SetupState":
        """Load state from file if exists, otherwise create new."""
        project_dir = project_dir or Path.cwd()
        state = cls(project_dir=project_dir)
        state_file = project_dir / SETUP_STATE_FILE
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                state.language = data.get("language", "en")
                state.slack_bot_token = data.get("slack_bot_token", "")
                state.slack_personal_token = data.get("slack_personal_token", "")
                state.slack_personal_cookie = data.get("slack_personal_cookie", "")
                state.slack_token_type = data.get("slack_token_type", "")
                state.bot_user_id = data.get("bot_user_id", "")
                state.trigger_mode = data.get("trigger_mode", "mention")
                state.custom_keyword = data.get("custom_keyword", "")
                state.permission_mode = data.get("permission_mode", "default")
                state.mcps_to_install = data.get("mcps_to_install", [])
                state.channels = data.get("channels", [])
                state.dashboard_port = data.get("dashboard_port", 7878)
                state.last_completed_step = data.get("last_completed_step", 0)
            except (json.JSONDecodeError, OSError):
                pass  # Use default state if file is corrupted
        return state

    def clear_saved_state(self) -> None:
        """Remove saved state file after successful completion."""
        state_file = self.project_dir / SETUP_STATE_FILE
        if state_file.exists():
            state_file.unlink()


def check_claude_code() -> CheckResult:
    """Check if Claude Code CLI is installed and logged in."""
    claude_path = shutil.which("claude")
    if not claude_path:
        return CheckResult(
            ok=False,
            message="Claude Code CLI is not installed",
            detail="Install from https://docs.anthropic.com/en/docs/claude-code\n"
            "npm install -g @anthropic-ai/claude-code",
        )

    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version = result.stdout.strip() or result.stderr.strip()
        if version:
            return CheckResult(ok=True, message=f"Claude Code {version}", detail=claude_path)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return CheckResult(
        ok=False,
        message="Claude Code version check failed",
        detail="The 'claude --version' command failed",
    )


def check_claude_login() -> CheckResult:
    """Check if Claude Code is authenticated."""
    # Check for auth files
    claude_dir = Path.home() / ".claude"
    if not claude_dir.exists():
        return CheckResult(
            ok=False,
            message="Claude Code login required",
            detail="Run 'claude' command to initiate automatic login",
        )

    # Check for files that indicate active Claude Code usage
    # Modern Claude Code uses settings.json and statsig directory
    settings_file = claude_dir / "settings.json"
    statsig_dir = claude_dir / "statsig"
    projects_dir = claude_dir / "projects"

    if settings_file.exists() or statsig_dir.exists() or projects_dir.exists():
        return CheckResult(ok=True, message="Claude Code authenticated", detail=str(claude_dir))

    return CheckResult(
        ok=False,
        message="Claude Code login required",
        detail="Run 'claude' command in terminal to log in",
    )


def check_uv() -> CheckResult:
    """Check if uv package manager is available."""
    uv_path = shutil.which("uv")
    if not uv_path:
        return CheckResult(
            ok=False,
            message="uv package manager is not installed",
            detail="curl -LsSf https://astral.sh/uv/install.sh | sh",
        )

    try:
        result = subprocess.run(["uv", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip()
        return CheckResult(ok=True, message=f"uv {version}", detail=uv_path)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return CheckResult(ok=False, message="uv version check failed", detail="")


def check_node() -> CheckResult:
    """Check if Node.js is available (needed for some MCPs)."""
    node_path = shutil.which("node")
    if not node_path:
        return CheckResult(
            ok=False,
            message="Node.js is not installed (required for some MCPs)",
            detail="Install from https://nodejs.org/",
        )

    try:
        result = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10)
        version = result.stdout.strip()
        return CheckResult(ok=True, message=f"Node.js {version}", detail=node_path)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return CheckResult(ok=False, message="Node.js version check failed", detail="")


def validate_slack_bot_token(token: str) -> CheckResult:
    """Validate a Slack bot token format."""
    token = token.strip()
    if not token:
        return CheckResult(ok=False, message="Token is empty", detail="")
    if token.startswith("xoxb-"):
        return CheckResult(ok=True, message="Bot token format verified", detail="xoxb-...")
    return CheckResult(
        ok=False,
        message="Invalid bot token format",
        detail="Bot token must start with 'xoxb-'",
    )


def validate_slack_personal_token(token: str) -> CheckResult:
    """Validate a Slack personal/user token format."""
    token = token.strip()
    if not token:
        return CheckResult(ok=False, message="Token is empty", detail="")
    if token.startswith("xoxc-"):
        return CheckResult(ok=True, message="Personal token format verified", detail="xoxc-...")
    if token.startswith("xoxp-"):
        return CheckResult(ok=True, message="User token format verified", detail="xoxp-...")
    return CheckResult(
        ok=False,
        message="Invalid personal token format",
        detail="Personal token must start with 'xoxc-' or 'xoxp-'",
    )


def validate_slack_cookie(cookie: str) -> CheckResult:
    """Validate a Slack cookie format."""
    cookie = cookie.strip()
    if not cookie:
        return CheckResult(ok=False, message="Cookie is empty", detail="")
    if cookie.startswith("xoxd-"):
        return CheckResult(ok=True, message="Cookie format verified", detail="xoxd-...")
    return CheckResult(
        ok=False,
        message="Invalid cookie format",
        detail="Cookie must start with 'xoxd-'",
    )


# --- MCP definitions ---

MCP_DEFINITIONS = {
    "slack-personal": {
        "name": "Slack Personal Token MCP",
        "description": "Full Slack features including DM, search with personal token",
        "install_cmd": "npm install -g @jtalk22/slack-mcp",
        "requires": ["node"],
        "env_vars": ["SLACK_TOKEN", "SLACK_COOKIE"],
        "mcp_config": {
            "command": "npx",
            "args": ["-y", "--package", "@jtalk22/slack-mcp", "slack-mcp-server"],
        },
        "guide": (
            "## Extracting from Browser DevTools\n\n"
            "### Step 1: Open Slack Web\n"
            "Go to https://app.slack.com/client/... in Chrome and log into your workspace\n"
            "(Must be logged in and on a workspace channel page)\n\n"
            "### Step 2: Open Developer Tools\n"
            "- Windows/Linux: F12 or Ctrl+Shift+I\n"
            "- macOS: Cmd+Option+I\n"
            "- Chrome: Menu(...) -> More tools -> Developer tools\n"
            "- Firefox: Menu -> Tools -> Browser tools -> Web Developer Tools\n"
            "- Edge: Menu(...) -> More tools -> Developer tools\n\n"
            "### Step 3: Extract xoxc Token (SLACK_TOKEN)\n"
            "1. Go to Console tab\n"
            "2. If you see a self-XSS warning, type 'allow pasting' and press Enter\n"
            "   (If it immediately shows a syntax error, ignore and continue)\n"
            "3. Paste the following command and press Enter:\n"
            "   JSON.parse(localStorage.localConfig_v2).teams[\n"
            "     Object.keys(JSON.parse(localStorage.localConfig_v2).teams)[0]\n"
            "   ].token\n"
            "4. Copy the output xoxc-... token\n\n"
            "### Step 4: Extract xoxd Cookie (SLACK_COOKIE)\n"
            "1. Click Application tab (Firefox: Storage tab)\n"
            "2. In left panel, select Cookies -> https://app.slack.com\n"
            "3. Find the 'd' cookie (value starts with xoxd-)\n"
            "4. Double-click the value to select, then copy (Ctrl+C / Cmd+C)\n\n"
            "### Auto Setup (macOS only)\n"
            "npm install -g @jtalk22/slack-mcp && slack-mcp-setup --setup\n"
            "(Auto-extracts if Slack is open in Chrome)\n\n"
            "Reference: https://github.com/korotovsky/slack-mcp-server/blob/master/docs/01-authentication-setup.md"
        ),
    },
    "slack-bot": {
        "name": "Slack Bot MCP",
        "description": "Send and read channel messages with Slack Bot token",
        "install_cmd": "npm install -g slack-bot-mcp",
        "requires": ["node"],
        "env_vars": ["SLACK_BOT_TOKEN"],
        "mcp_config": {
            "command": "npx",
            "args": ["-y", "slack-bot-mcp"],
            "env": {"SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}"},
        },
        "guide": (
            "1. Create a new app at https://api.slack.com/apps\n"
            "2. Add Bot Token Scopes in OAuth & Permissions:\n"
            "   - channels:history, channels:read, chat:write\n"
            "   - groups:history, groups:read, im:history, im:read\n"
            "   - mpim:history, mpim:read, users:read\n"
            "   - files:write, files:read, reactions:write\n"
            "3. Install the app to your workspace\n"
            "4. Copy the Bot User OAuth Token (xoxb-...)"
        ),
    },
    "playwright": {
        "name": "Playwright MCP",
        "description": "Browser automation (E2E testing, web scraping)",
        "install_cmd": "npx playwright install",
        "requires": ["node"],
        "env_vars": [],
        "mcp_config": {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
        },
        "guide": (
            "## Prerequisites (Required)\n"
            "1. Verify Node.js 18+ is installed: node --version\n"
            "2. Install browser binaries:\n"
            "   npx playwright install\n"
            "   (Downloads Chromium, Firefox, WebKit - ~500MB)\n\n"
            "## Verify Installation\n"
            "npx playwright --version\n\n"
            "Reference: https://github.com/microsoft/playwright-mcp"
        ),
    },
    "context7": {
        "name": "Context7 MCP",
        "description": "Real-time library documentation lookup",
        "install_cmd": None,
        "requires": ["node"],
        "env_vars": [],
        "mcp_config": {
            "command": "npx",
            "args": ["-y", "@upstash/context7-mcp@latest"],
        },
        "guide": (
            "## Prerequisites\n"
            "1. Verify Node.js 18+ is installed: node --version\n\n"
            "## Optional\n"
            "- Get API key for higher rate limits:\n"
            "  https://context7.com/dashboard\n\n"
            "Reference: https://github.com/upstash/context7"
        ),
    },
    "sequential-thinking": {
        "name": "Sequential Thinking MCP",
        "description": "Step-by-step thinking process support",
        "install_cmd": None,
        "requires": ["node"],
        "env_vars": [],
        "mcp_config": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
        },
        "guide": (
            "## Prerequisites\n"
            "1. Verify Node.js 18+ is installed: node --version\n\n"
            "## Usage\n"
            "Runs automatically via NPX.\n\n"
            "## Environment Variables (Optional)\n"
            "DISABLE_THOUGHT_LOGGING=true  # Disable logging\n\n"
            "Reference: https://github.com/modelcontextprotocol/servers/tree/main/src/sequentialthinking"
        ),
    },
}


def get_claude_mcp_config_path() -> Path:
    """Get path to Claude Code's MCP config."""
    return Path.cwd() / ".mcp.json"


def read_mcp_config(path: Path | None = None) -> dict:
    """Read existing MCP config."""
    config_path = path or get_claude_mcp_config_path()
    if config_path.exists():
        with open(config_path) as f:
            return json.load(f)
    return {"mcpServers": {}}


def write_mcp_config(config: dict, path: Path | None = None) -> None:
    """Write MCP config."""
    config_path = path or get_claude_mcp_config_path()
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def generate_env_file(state: SetupState) -> str:
    """Generate .env file content."""
    lines = ["# Ultraworker Environment Configuration", "# Generated by setup wizard", ""]
    env_vars = state.get_env_vars()
    for key, value in env_vars.items():
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def generate_ultrawork_yaml(state: SetupState) -> str:
    """Generate ultrawork.yaml content."""
    trigger = f"<@{state.bot_user_id}>" if state.trigger_mode == "mention" else state.custom_keyword

    yaml_content = f"""data_dir: data
executor:
  claude_command: claude
  codex_command: codex
  default_executor: claude
  timeout_seconds: 6000
language:
  default: "{state.language}"
polling:
  enabled: false
  explore_depth: 2
  max_consecutive_errors: 5
  max_messages_per_poll: 50
  max_processed_cache: 10000
  max_thread_history: 100
  poll_interval_seconds: 10
response:
  auto_respond: true
  auto_types:
  - acknowledge
  - simple_query
  - action
  - complex
  - defer
  confidence_threshold: 0.8
  manual_types:
slack:
  bot_user_id: {state.bot_user_id}
  default_channel: ""
  trigger_pattern: "{trigger}"
workflow:
  auto_approve_simple_tasks: false
  default_workflow_type: full
  require_tech_spec_for_code: true
"""
    return yaml_content


def generate_mcp_json(state: SetupState) -> dict:
    """Generate .mcp.json content based on setup state."""
    config = {"mcpServers": {}}

    # Add Slack MCPs based on token type
    if state.slack_personal_token:
        slack_personal = MCP_DEFINITIONS["slack-personal"]["mcp_config"].copy()
        env = {}
        if state.slack_personal_token:
            env["SLACK_TOKEN"] = state.slack_personal_token
        if state.slack_personal_cookie:
            env["SLACK_COOKIE"] = state.slack_personal_cookie
        if env:
            slack_personal["env"] = env
        config["mcpServers"]["slack"] = slack_personal

    if state.slack_bot_token:
        slack_bot = MCP_DEFINITIONS["slack-bot"]["mcp_config"].copy()
        slack_bot["env"] = {"SLACK_BOT_TOKEN": state.slack_bot_token}
        config["mcpServers"]["slack-bot-mcp"] = slack_bot

    # Add selected MCPs
    for mcp_id in state.mcps_to_install:
        if mcp_id in MCP_DEFINITIONS and mcp_id not in ("slack-personal", "slack-bot"):
            defn = MCP_DEFINITIONS[mcp_id]
            config["mcpServers"][mcp_id] = defn["mcp_config"].copy()

    return config


def _get_language_name(code: str) -> str:
    """Get full language name from code."""
    from ultrawork.config import SUPPORTED_LANGUAGES
    return SUPPORTED_LANGUAGES.get(code, code)


def update_claude_md_for_tokens(project_dir: Path, state: SetupState) -> None:
    """Update CLAUDE.md to reflect available token types and language settings.

    Always replaces existing Token Configuration Note and Language Configuration
    sections to ensure they reflect the current settings.
    """
    claude_md = project_dir / "CLAUDE.md"
    if not claude_md.exists():
        return

    content = claude_md.read_text()

    # Remove existing Token Configuration Note section if present
    import re
    content = re.sub(
        r'\n*## Token Configuration Note\n.*?(?=\n## |\Z)',
        '',
        content,
        flags=re.DOTALL
    )

    # Remove existing Language Configuration section if present
    content = re.sub(
        r'\n*## Language Configuration\n.*?(?=\n## |\Z)',
        '',
        content,
        flags=re.DOTALL
    )
    content = content.rstrip()

    # Add Language Configuration section
    lang_code = state.language or "en"
    lang_name = _get_language_name(lang_code)

    lang_note = (
        f"\n\n\n## Language Configuration\n\n"
        f"System language is set to **{lang_name}** (`{lang_code}`).\n\n"
        f"**IMPORTANT**: All the following MUST be in {lang_name}:\n"
        f"- All Slack messages and responses\n"
        f"- All thinking and reasoning output\n"
        f"- All skill execution output (TODO items, specs, reports, approval messages)\n"
        f"- All error messages and status updates sent to Slack\n"
        f"- All user-facing CLI output\n"
        f"- All exploration summaries and context analysis\n\n"
        f"Technical terms, code identifiers, file paths, and command names should remain in their original form.\n"
    )

    content += lang_note

    # Determine token configuration and create appropriate note
    has_bot = bool(state.slack_bot_token)
    has_personal = bool(state.slack_personal_token)

    if has_bot and has_personal:
        note = (
            "\n\n\n## Token Configuration Note\n\n"
            "Both Bot token and personal token are configured in this installation.\n"
            "- `mcp__slack__` tools available (personal token based)\n"
            "- `mcp__slack-bot-mcp__` tools available (Bot token based)\n"
            "- Fallback strategy enabled (uses Fallback when Primary fails)\n"
        )
    elif has_bot and not has_personal:
        note = (
            "\n\n\n## Token Configuration Note\n\n"
            "Only Bot token is configured in this installation.\n"
            "- `mcp__slack__` (personal token MCP) tools are not available\n"
            "- Only `mcp__slack-bot-mcp__` tools are available\n"
            "- Search functionality (`slack_search_messages`) is not available\n"
        )
    elif has_personal and not has_bot:
        note = (
            "\n\n\n## Token Configuration Note\n\n"
            "Only personal token is configured in this installation.\n"
            "- `mcp__slack-bot-mcp__` tools are not available\n"
            "- Only `mcp__slack__` tools are available\n"
            "- Bot-only features like `slack_add_reaction` are not available\n"
        )
    else:
        note = (
            "\n\n\n## Token Configuration Note\n\n"
            "**Warning**: No Slack tokens are configured.\n"
            "- Slack MCP tools cannot be used\n"
            "- Run the setup wizard to configure tokens: `uv run ultrawork setup`\n"
        )

    content += note
    claude_md.write_text(content)
