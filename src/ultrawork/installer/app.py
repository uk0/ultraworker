"""Textual TUI Setup Wizard for Ultraworker."""

from __future__ import annotations

import json
import select
import shutil
import shlex
import subprocess
import sys
import time
from pathlib import Path


def copy_to_clipboard(text: str) -> tuple[bool, str]:
    """Copy text to system clipboard. Returns (success, detail)."""
    commands: list[list[str]] = []

    if sys.platform == "darwin":
        commands = [["pbcopy"]]
    elif sys.platform == "win32":
        commands = [["clip"]]
    else:
        # Linux/WSL: try Windows clipboard bridge first, then native tools.
        commands = [
            ["clip.exe"],
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]

    attempted: list[str] = []
    for cmd in commands:
        if shutil.which(cmd[0]) is None:
            continue
        attempted.append(cmd[0])
        try:
            subprocess.run(cmd, input=text.encode(), check=True)
            return True, f"Copied via {cmd[0]}"
        except Exception:
            continue

    if attempted:
        return False, f"Clipboard command failed ({', '.join(attempted)})"
    return False, "No clipboard command found (clip.exe, wl-copy, xclip, xsel)"


# JavaScript for extracting xoxc token
XOXC_SCRIPT = (
    "JSON.parse(localStorage.localConfig_v2).teams"
    "[Object.keys(JSON.parse(localStorage.localConfig_v2).teams)[0]].token"
)

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    Markdown,
    RadioButton,
    RadioSet,
    Rule,
    Static,
)

from ultrawork.installer.checks import (
    MCP_DEFINITIONS,
    SETUP_STATE_FILE,
    CheckResult,
    SetupState,
    check_claude_code,
    check_claude_login,
    check_node,
    check_uv,
    generate_env_file,
    generate_mcp_json,
    generate_ultrawork_yaml,
    update_claude_md_for_tokens,
    validate_slack_bot_token,
    validate_slack_cookie,
    validate_slack_personal_token,
)

WELCOME_MD = """\
# 🚀 Ultraworker Setup Wizard

Configure your Slack mention-based automated task processing system.

## Setup Steps

| Step | Description |
|------|-------------|
| 0 | Select language |
| 1 | Verify Claude Code login |
| 2 | Configure Slack tokens |
| 3 | Basic settings (mention detection/permissions) |
| 4 | Install additional MCPs |
| 5 | Extract Slack channels |
| 6 | Tutorial |
| 7 | Launch dashboard |

**Press the Next button to begin.**
"""

# Language options for setup wizard
LANGUAGE_OPTIONS = {
    "en": "English",
    "ko": "한국어 (Korean)",
    "ja": "日本語 (Japanese)",
    "zh": "中文 (Chinese)",
    "es": "Español (Spanish)",
    "fr": "Français (French)",
    "de": "Deutsch (German)",
    "pt": "Português (Portuguese)",
}

TUTORIAL_MD = """\
# 📖 How to Use Ultraworker

## Basic Usage

1. **Mention the bot on Slack**: `@ultraworker analyze this thread`
2. **Automatic response**: The bot analyzes context and responds
3. **Start workflow**: Complex tasks proceed in order: TODO → Spec → Implementation → Report

## Claude Code Skills

| Command | Description |
|---------|-------------|
| `/explore-context` | Explore thread/keyword context |
| `/create-todo` | Generate TODO list |
| `/write-spec` | Write tech spec |
| `/approve` | Approve stage |
| `/reject` | Request revision |
| `/report` | Generate final report |

## CLI Commands

```bash
ultrawork task:list        # List tasks
ultrawork dashboard        # Start dashboard
ultrawork daemon:start     # Start polling daemon
ultrawork poll:status      # Check polling status
```

## Dashboard

```bash
ultrawork dashboard --port 7878
```

Access `http://localhost:7878` in your browser to view real-time workflows.

## Permission Modes

- **Default mode**: Approval required for each tool execution
- **Dangerous Skip**: All tools auto-approved (use with caution!)

Change settings: `claude --permission-mode <mode>`
"""


class WelcomeScreen(Screen):
    """Welcome screen with setup overview."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Markdown(WELCOME_MD)
            yield Static("", id="resume-notice")
        with Center():
            with Horizontal(classes="button-row"):
                yield Button("Next →", variant="primary", id="btn-next")
        yield Footer()

    def on_mount(self) -> None:
        # Check if there's saved state from previous session
        state_file = Path.cwd() / SETUP_STATE_FILE
        if state_file.exists():
            app = self.app
            if isinstance(app, SetupWizardApp) and app.state.last_completed_step > 0:
                step_names = ["Start", "Claude Check", "Slack Tokens", "Basic Settings", "MCP Install", "Channels", "Tutorial"]
                last_step = min(app.state.last_completed_step, len(step_names) - 1)
                self.query_one("#resume-notice", Static).update(
                    f"💾 Previous settings found (last step: {step_names[last_step]})\n"
                    "   Your previously entered values will be restored automatically."
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.app.action_next_step()


class Step0LanguageSelect(Screen):
    """Step 0: Language selection."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 0/7: Select Language / 언어 선택", classes="step-title")
            yield Rule()
            yield Static(
                "Select the language for Ultraworker.\n"
                "This affects all Slack responses, thinking output, and system messages.\n\n"
                "Ultraworker의 언어를 선택하세요.\n"
                "Slack 응답, thinking 출력, 시스템 메시지 등에 반영됩니다."
            )
            yield Rule()
            with RadioSet(id="language-select"):
                for code, label in LANGUAGE_OPTIONS.items():
                    is_default = code == "en"
                    yield RadioButton(label, id=f"radio-lang-{code}", value=is_default)
                yield RadioButton("Custom (type your own)", id="radio-lang-custom")
            yield Static(
                "Enter a language code (e.g. vi, th, ar) or name:",
                id="custom-lang-label",
            )
            yield Input(
                placeholder="e.g. vi, th, ar, Tiếng Việt, ภาษาไทย ...",
                id="custom-lang-input",
            )

        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app
        if isinstance(app, SetupWizardApp):
            lang = app.state.language or "en"
            if lang in LANGUAGE_OPTIONS:
                radio_id = f"radio-lang-{lang}"
                try:
                    self.query_one(f"#{radio_id}", RadioButton).value = True
                except Exception:
                    pass
            else:
                # Custom language was previously set
                try:
                    self.query_one("#radio-lang-custom", RadioButton).value = True
                    self.query_one("#custom-lang-input", Input).value = lang
                except Exception:
                    pass
        self._toggle_custom_input()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        self._toggle_custom_input()

    def _toggle_custom_input(self) -> None:
        """Show/hide custom language input based on radio selection."""
        lang_set = self.query_one("#language-select", RadioSet)
        is_custom = (
            lang_set.pressed_button is not None
            and lang_set.pressed_button.id == "radio-lang-custom"
        )
        self.query_one("#custom-lang-label", Static).display = is_custom
        self.query_one("#custom-lang-input", Input).display = is_custom

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._save_language()
            self.app.action_next_step()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()

    def _save_language(self) -> None:
        app = self.app
        if not isinstance(app, SetupWizardApp):
            return

        lang_set = self.query_one("#language-select", RadioSet)
        if lang_set.pressed_button and lang_set.pressed_button.id:
            if lang_set.pressed_button.id == "radio-lang-custom":
                custom_value = self.query_one("#custom-lang-input", Input).value.strip()
                app.state.language = custom_value if custom_value else "en"
            else:
                # Extract language code from radio button id: "radio-lang-en" -> "en"
                lang_code = lang_set.pressed_button.id.replace("radio-lang-", "")
                app.state.language = lang_code
        else:
            app.state.language = "en"


class Step1ClaudeCheck(Screen):
    """Step 1: Check Claude Code installation and login."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 1/7: Claude Code Verification", classes="step-title")
            yield Rule()
            yield Static("Checking system requirements...", id="check-status")
            yield Static("", id="check-claude")
            yield Static("", id="check-login")
            yield Static("", id="check-uv")
            yield Static("", id="check-node")
        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("Re-check", variant="warning", id="btn-recheck")
                yield Button("Next →", variant="primary", id="btn-next", disabled=True)
        yield Footer()

    def on_mount(self) -> None:
        self.run_checks()

    @work(thread=True)
    def run_checks(self) -> None:
        results = {}

        # Claude Code
        result = check_claude_code()
        results["claude"] = result
        self.app.call_from_thread(self._update_check, "check-claude", "Claude Code CLI", result)

        # Login
        result = check_claude_login()
        results["login"] = result
        self.app.call_from_thread(self._update_check, "check-login", "Claude Code Auth", result)

        # uv
        result = check_uv()
        results["uv"] = result
        self.app.call_from_thread(self._update_check, "check-uv", "uv Package Manager", result)

        # Node.js
        result = check_node()
        results["node"] = result
        self.app.call_from_thread(self._update_check, "check-node", "Node.js", result)

        # Check if critical items passed
        critical_ok = results["claude"].ok and results["uv"].ok
        self.app.call_from_thread(self._finish_checks, critical_ok)

    def _update_check(self, widget_id: str, name: str, result: CheckResult) -> None:
        icon = "✅" if result.ok else "❌"
        widget = self.query_one(f"#{widget_id}", Static)
        text = f"{icon} {name}: {result.message}"
        if result.detail and not result.ok:
            text += f"\n   → {result.detail}"
        widget.update(text)

    def _finish_checks(self, critical_ok: bool) -> None:
        status = self.query_one("#check-status", Static)
        btn = self.query_one("#btn-next", Button)
        if critical_ok:
            status.update("✅ Required prerequisites verified!")
            btn.disabled = False
            app = self.app
            if isinstance(app, SetupWizardApp):
                app.state.claude_logged_in = True
        else:
            status.update("⚠️ Please install required prerequisites first")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.app.action_next_step()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()
        elif event.button.id == "btn-recheck":
            for wid in ["check-claude", "check-login", "check-uv", "check-node"]:
                self.query_one(f"#{wid}", Static).update("⏳ Checking...")
            self.query_one("#btn-next", Button).disabled = True
            self.run_checks()


class Step2SlackTokens(Screen):
    """Step 2: Slack token configuration."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 2/7: Slack Token Configuration", classes="step-title")
            yield Rule()

            yield Label("Which token type will you use?")
            with RadioSet(id="token-type"):
                yield RadioButton("Bot token only (xoxb-)", id="radio-bot")
                yield RadioButton("Personal token only (xoxc- + xoxd-)", id="radio-personal")
                yield RadioButton("Both (recommended)", id="radio-both", value=True)

            yield Rule(id="rule-token-sections-start")

            # Bot token section
            yield Label("🤖 Bot Token (xoxb-...)", id="lbl-bot")
            yield Static(
                "1. Create an app at https://api.slack.com/apps\n"
                "2. Go to OAuth & Permissions → Bot Token Scopes\n"
                "3. Add ALL required scopes:\n"
                "   channels:history, channels:read, chat:write,\n"
                "   groups:history, groups:read, im:history, im:read,\n"
                "   mpim:history, mpim:read, users:read,\n"
                "   files:write, files:read, reactions:write\n"
                "4. Install app to workspace → Copy Bot User OAuth Token",
                id="guide-bot",
                classes="guide-text",
            )
            yield Input(
                placeholder="xoxb-xxxx-xxxx-xxxx",
                password=True,
                id="input-bot-token",
            )
            yield Static("", id="status-bot-token")

            yield Rule(id="rule-token-sections-middle")

            # Personal token section
            yield Label("👤 Personal Token (xoxc-...)", id="lbl-personal")
            yield Static(
                "1. Open https://app.slack.com/client/... in Chrome and log in to your workspace\n"
                "   (Must be logged in and on a workspace channel page)\n"
                "2. Press F12 (Mac: Cmd+Opt+I) → Console tab\n"
                "3. If self-XSS warning appears, type 'allow pasting' and press Enter\n"
                "   (If it shows syntax error immediately, ignore and continue)\n"
                "4. Paste the script below into Console and press Enter\n"
                "5. Copy the output xoxc-... token",
                id="guide-personal",
                classes="guide-text",
            )
            yield Static(
                f"Script: {XOXC_SCRIPT[:40]}...",
                id="script-preview",
                classes="guide-text",
            )
            with Center():
                yield Button("Copy Script", id="btn-copy-script", variant="warning")
            yield Static("", id="copy-status")
            yield Static("", id="manual-script", classes="guide-text")
            yield Input(
                placeholder="Copy script will appear here if automatic copy fails",
                id="manual-script-input",
            )
            yield Input(
                placeholder="xoxc-xxxx-xxxx",
                password=True,
                id="input-personal-token",
            )
            yield Static("", id="status-personal-token")

            yield Label("🍪 Cookie (xoxd-...)", id="lbl-cookie")
            yield Static(
                "1. In DevTools, click the Application tab (Firefox: Storage)\n"
                "2. Cookies → Select https://app.slack.com\n"
                "3. Find the 'd' cookie → Double-click the value → Copy",
                id="guide-cookie",
                classes="guide-text",
            )
            yield Input(
                placeholder="xoxd-xxxx",
                password=True,
                id="input-cookie",
            )
            yield Static("", id="status-cookie")

        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app
        if isinstance(app, SetupWizardApp):
            state = app.state
            if state.slack_bot_token:
                self.query_one("#input-bot-token", Input).value = state.slack_bot_token
            if state.slack_personal_token:
                self.query_one("#input-personal-token", Input).value = state.slack_personal_token
            if state.slack_personal_cookie:
                self.query_one("#input-cookie", Input).value = state.slack_personal_cookie

            token_type = state.slack_token_type
            if not token_type:
                if state.slack_bot_token and state.slack_personal_token:
                    token_type = "both"
                elif state.slack_bot_token:
                    token_type = "bot"
                elif state.slack_personal_token:
                    token_type = "personal"
                else:
                    token_type = "both"
            self._set_token_type(token_type)

        self.query_one("#manual-script", Static).display = False
        self.query_one("#manual-script-input", Input).display = False

    @on(RadioSet.Changed, "#token-type")
    def on_token_type_change(self, event: RadioSet.Changed) -> None:
        selected_id = event.pressed.id if event.pressed else None
        self._update_token_visibility(selected_id)

    def _set_token_type(self, token_type: str) -> None:
        if token_type == "bot":
            self.query_one("#radio-bot", RadioButton).value = True
            self._update_token_visibility("radio-bot")
        elif token_type == "personal":
            self.query_one("#radio-personal", RadioButton).value = True
            self._update_token_visibility("radio-personal")
        else:
            self.query_one("#radio-both", RadioButton).value = True
            self._update_token_visibility("radio-both")

    def _update_token_visibility(self, selected_id: str | None) -> None:
        show_bot = selected_id in ("radio-bot", "radio-both")
        show_personal = selected_id in ("radio-personal", "radio-both")

        # Bot token fields
        self.query_one("#lbl-bot", Label).display = show_bot
        self.query_one("#guide-bot", Static).display = show_bot
        self.query_one("#input-bot-token", Input).display = show_bot
        self.query_one("#status-bot-token", Static).display = show_bot

        # Personal token + cookie fields
        self.query_one("#lbl-personal", Label).display = show_personal
        self.query_one("#guide-personal", Static).display = show_personal
        self.query_one("#script-preview", Static).display = show_personal
        self.query_one("#btn-copy-script", Button).display = show_personal
        self.query_one("#copy-status", Static).display = show_personal
        self.query_one("#manual-script", Static).display = False
        self.query_one("#manual-script-input", Input).display = False
        self.query_one("#input-personal-token", Input).display = show_personal
        self.query_one("#status-personal-token", Static).display = show_personal
        self.query_one("#lbl-cookie", Label).display = show_personal
        self.query_one("#guide-cookie", Static).display = show_personal
        self.query_one("#input-cookie", Input).display = show_personal
        self.query_one("#status-cookie", Static).display = show_personal

        # Divider between sections should appear only in "both" mode.
        self.query_one("#rule-token-sections-middle", Rule).display = show_bot and show_personal

    @on(Input.Changed, "#input-bot-token")
    def validate_bot(self, event: Input.Changed) -> None:
        if event.value:
            result = validate_slack_bot_token(event.value)
            icon = "✅" if result.ok else "❌"
            self.query_one("#status-bot-token", Static).update(f"{icon} {result.message}")
        else:
            self.query_one("#status-bot-token", Static).update("")

    @on(Input.Changed, "#input-personal-token")
    def validate_personal(self, event: Input.Changed) -> None:
        if event.value:
            result = validate_slack_personal_token(event.value)
            icon = "✅" if result.ok else "❌"
            self.query_one("#status-personal-token", Static).update(f"{icon} {result.message}")
        else:
            self.query_one("#status-personal-token", Static).update("")

    @on(Input.Changed, "#input-cookie")
    def validate_cookie(self, event: Input.Changed) -> None:
        if event.value:
            result = validate_slack_cookie(event.value)
            icon = "✅" if result.ok else "❌"
            self.query_one("#status-cookie", Static).update(f"{icon} {result.message}")
        else:
            self.query_one("#status-cookie", Static).update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._save_tokens()
            self.app.action_next_step()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()
        elif event.button.id == "btn-copy-script":
            copied, detail = copy_to_clipboard(XOXC_SCRIPT)
            manual = self.query_one("#manual-script", Static)
            manual_input = self.query_one("#manual-script-input", Input)
            if copied:
                self.query_one("#copy-status", Static).update("✅ Copied to clipboard!")
                manual.update("")
                manual.display = False
                manual_input.value = ""
                manual_input.display = False
            else:
                self.query_one("#copy-status", Static).update(
                    f"❌ Copy failed ({detail}) - showing full script below"
                )
                manual.update("Full Script (select and copy):")
                manual.display = True
                manual_input.value = XOXC_SCRIPT
                manual_input.display = True

    def _save_tokens(self) -> None:
        app = self.app
        if not isinstance(app, SetupWizardApp):
            return

        selected_token_type = "both"
        token_set = self.query_one("#token-type", RadioSet)
        if token_set.pressed_button and token_set.pressed_button.id == "radio-bot":
            selected_token_type = "bot"
        elif token_set.pressed_button and token_set.pressed_button.id == "radio-personal":
            selected_token_type = "personal"

        bot = self.query_one("#input-bot-token", Input).value.strip()
        personal = self.query_one("#input-personal-token", Input).value.strip()
        cookie = self.query_one("#input-cookie", Input).value.strip()

        app.state.slack_token_type = selected_token_type
        if selected_token_type == "bot":
            app.state.slack_bot_token = bot
            app.state.slack_personal_token = ""
            app.state.slack_personal_cookie = ""
        elif selected_token_type == "personal":
            app.state.slack_bot_token = ""
            app.state.slack_personal_token = personal
            app.state.slack_personal_cookie = cookie
        else:
            app.state.slack_bot_token = bot
            app.state.slack_personal_token = personal
            app.state.slack_personal_cookie = cookie


class Step3BasicSettings(Screen):
    """Step 3: Basic settings."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 3/7: Basic Settings", classes="step-title")
            yield Rule()

            yield Label("Trigger Mode")
            with RadioSet(id="trigger-mode"):
                yield RadioButton(
                    "@Mention detection (responds when bot is @mentioned)", id="radio-mention", value=True
                )
                yield RadioButton("Custom keyword detection", id="radio-keyword")

            # Bot ID input (shown when mention mode selected)
            yield Label("Bot User ID (Bot's Member ID in Slack)", id="lbl-bot-id")
            yield Static(
                "In Slack, click bot profile → ⋮ menu → Copy member ID",
                id="guide-bot-id",
                classes="guide-text",
            )
            yield Input(placeholder="U0XXXXXXXXX", id="input-bot-user-id")

            # Keyword input (shown when keyword mode selected)
            yield Label("Custom Keyword", id="lbl-keyword")
            yield Static(
                "The bot will respond to messages containing this keyword",
                id="guide-keyword",
                classes="guide-text",
            )
            yield Input(placeholder="e.g., !ultrawork, /ask", id="input-keyword")

            yield Rule()
            yield Label("Permission Mode")
            with RadioSet(id="permission-mode"):
                yield RadioButton(
                    "Default mode (approval required for tool execution)", id="radio-default-perm", value=True
                )
                yield RadioButton(
                    "🚀 YOLO mode (all tools auto-approved)",
                    id="radio-dangerous-perm",
                )

            yield Static("", id="permission-warning")

        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")
        yield Footer()

    def on_mount(self) -> None:
        app = self.app
        if isinstance(app, SetupWizardApp):
            state = app.state
            if state.bot_user_id:
                self.query_one("#input-bot-user-id", Input).value = state.bot_user_id
            if state.custom_keyword:
                self.query_one("#input-keyword", Input).value = state.custom_keyword
        # Initial visibility
        self._update_trigger_visibility("radio-mention")

    @on(RadioSet.Changed, "#trigger-mode")
    def on_trigger_change(self, event: RadioSet.Changed) -> None:
        self._update_trigger_visibility(event.pressed.id)

    def _update_trigger_visibility(self, selected_id: str | None) -> None:
        is_mention = selected_id == "radio-mention"
        # Bot ID fields
        self.query_one("#lbl-bot-id", Label).display = is_mention
        self.query_one("#guide-bot-id", Static).display = is_mention
        self.query_one("#input-bot-user-id", Input).display = is_mention
        # Keyword fields
        self.query_one("#lbl-keyword", Label).display = not is_mention
        self.query_one("#guide-keyword", Static).display = not is_mention
        self.query_one("#input-keyword", Input).display = not is_mention

    @on(RadioSet.Changed, "#permission-mode")
    def on_permission_change(self, event: RadioSet.Changed) -> None:
        warning = self.query_one("#permission-warning", Static)
        if event.pressed.id == "radio-dangerous-perm":
            warning.update(
                "🚀 YOLO! Claude will execute all tools without approval.\n"
                "   (file modifications, command execution, etc. - use only in trusted environments!)"
            )
        else:
            warning.update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._save_settings()
            self.app.action_next_step()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()

    def _save_settings(self) -> None:
        app = self.app
        if not isinstance(app, SetupWizardApp):
            return

        app.state.bot_user_id = self.query_one("#input-bot-user-id", Input).value.strip()

        # Trigger mode
        trigger_set = self.query_one("#trigger-mode", RadioSet)
        if trigger_set.pressed_button and trigger_set.pressed_button.id == "radio-keyword":
            app.state.trigger_mode = "keyword"
            app.state.custom_keyword = self.query_one("#input-keyword", Input).value.strip()
        else:
            app.state.trigger_mode = "mention"

        # Permission mode
        perm_set = self.query_one("#permission-mode", RadioSet)
        if perm_set.pressed_button and perm_set.pressed_button.id == "radio-dangerous-perm":
            app.state.permission_mode = "dangerously-skip-permissions"
        else:
            app.state.permission_mode = "default"


class Step4MCPInstall(Screen):
    """Step 4: MCP installation options."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 4/7: Additional MCP Installation", classes="step-title")
            yield Rule()
            yield Static("Slack MCP is automatically configured based on token settings.\nSelect additional MCPs to install:")

            yield Rule()
            # Non-Slack MCPs
            for mcp_id, defn in MCP_DEFINITIONS.items():
                if mcp_id in ("slack-personal", "slack-bot"):
                    continue
                yield Checkbox(
                    f"{defn['name']}: {defn['description']}",
                    id=f"mcp-{mcp_id}",
                )
                yield Static(f"  Guide: {defn['guide']}", classes="guide-text")

            yield Rule()
            yield Static("", id="mcp-install-status")

        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self._save_mcps()
            self.app.action_next_step()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()

    def _save_mcps(self) -> None:
        app = self.app
        if not isinstance(app, SetupWizardApp):
            return

        selected = []
        for mcp_id in MCP_DEFINITIONS:
            if mcp_id in ("slack-personal", "slack-bot"):
                continue
            try:
                cb = self.query_one(f"#mcp-{mcp_id}", Checkbox)
                if cb.value:
                    selected.append(mcp_id)
            except Exception:
                pass

        app.state.mcps_to_install = selected


class Step5Channels(Screen):
    """Step 5: Extract Slack channels."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 5/7: Extract Slack Channel List", classes="step-title")
            yield Rule()
            yield Static(
                "After setup, you can sync channels with the /sync-slack command in Claude Code.\n\n"
                "If your configured tokens are valid, the channel list will be fetched automatically on first run.",
                id="channel-info",
            )
            yield Rule()
            yield Static(
                "📋 How to Sync Channels:\n\n"
                "1. Run Claude Code after installation\n"
                "2. Enter the /sync-slack command\n"
                "3. Channel list is saved to data/registry/channels.yaml\n"
                "4. Select channels to monitor: ultrawork slack:set-monitor <channel-id>",
            )
        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.app.action_next_step()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()


class Step6Tutorial(Screen):
    """Step 6: Tutorial."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 6/7: Tutorial", classes="step-title")
            yield Rule()
            yield Markdown(TUTORIAL_MD)
        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("Next →", variant="primary", id="btn-next")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-next":
            self.app.action_next_step()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()


class Step7Finish(Screen):
    """Step 7: Apply configuration and launch dashboard."""

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Label("Step 7/7: Apply Settings & Dashboard", classes="step-title")
            yield Rule()
            yield Static("", id="summary")
            yield Rule()
            yield Static("", id="apply-status")
        with Center():
            with Horizontal(classes="button-row"):
                yield Button("← Back", id="btn-back")
                yield Button("✅ Apply Settings", variant="success", id="btn-apply")
                yield Button(
                    "🚀 Start Dashboard", variant="primary", id="btn-dashboard", disabled=True
                )
        yield Footer()

    def on_mount(self) -> None:
        app = self.app
        if not isinstance(app, SetupWizardApp):
            return

        state = app.state
        lines = ["📋 Configuration Summary\n"]
        lang_label = LANGUAGE_OPTIONS.get(state.language, f"{state.language} (Custom)")
        lines.append(f"  Language: {lang_label}")
        lines.append(f"  Token Type: {state.slack_token_type or '(not set)'}")
        if state.trigger_mode == "mention":
            lines.append(f"  Trigger Mode: @Mention detection")
            lines.append(f"  Bot User ID: {state.bot_user_id or '(not set)'}")
        else:
            lines.append(f"  Trigger Mode: Custom keyword")
            lines.append(f"  Custom Keyword: {state.custom_keyword or '(not set)'}")
        perm_display = "🚀 YOLO Mode" if state.permission_mode == "dangerously-skip-permissions" else "Default Mode"
        lines.append(f"  Permission Mode: {perm_display}")
        lines.append(f"  Additional MCPs: {', '.join(state.mcps_to_install) or 'None'}")

        lines.append("\n📁 Files to be created:")
        lines.append("  • .env (environment variables)")
        lines.append("  • ultrawork.yaml (main config)")
        lines.append("  • .mcp.json (MCP server config)")
        lines.append("  • data/ directory initialization")

        self.query_one("#summary", Static).update("\n".join(lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-apply":
            self.apply_config()
        elif event.button.id == "btn-back":
            self.app.action_prev_step()
        elif event.button.id == "btn-dashboard":
            self.launch_dashboard()

    @work(thread=True)
    def apply_config(self) -> None:
        app = self.app
        if not isinstance(app, SetupWizardApp):
            return

        state = app.state
        project_dir = state.project_dir
        status_lines = []
        install_timeout_seconds = 1800  # 30 minutes

        def update_status(msg: str) -> None:
            status_lines.append(msg)
            self.app.call_from_thread(
                self.query_one("#apply-status", Static).update, "\n".join(status_lines)
            )

        def run_with_progress(
            cmd: list[str],
            *,
            cwd: Path | None = None,
            heartbeat_label: str = "Installing...",
        ) -> tuple[bool, str]:
            """Run command with periodic progress updates and live output."""
            def _append_output(raw_output: str) -> None:
                if not raw_output:
                    return
                for line in raw_output.replace("\r", "\n").split("\n"):
                    text_line = line.strip()
                    if text_line:
                        update_status(f"  ⏳ {text_line}")

            try:
                process = subprocess.Popen(
                    cmd,
                    cwd=str(cwd) if cwd else None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=False,
                    bufsize=0,
                )
            except Exception as e:
                return False, str(e)

            start = time.monotonic()
            last_heartbeat = -1
            output_buffer = ""
            try:
                while True:
                    if process.stdout:
                        ready, _, _ = select.select([process.stdout], [], [], 1.0)
                        if ready:
                            read_chunk = (
                                process.stdout.read1(4096)
                                if hasattr(process.stdout, "read1")
                                else process.stdout.read(4096)
                            )
                            if read_chunk:
                                chunk = (
                                    read_chunk.decode("utf-8", errors="replace")
                                    if isinstance(read_chunk, (bytes, bytearray))
                                    else str(read_chunk)
                                )
                                output_buffer += chunk.replace("\r", "\n")
                                lines = output_buffer.split("\n")
                                if output_buffer.endswith("\n"):
                                    output_buffer = ""
                                    complete_lines = lines
                                else:
                                    complete_lines = lines[:-1]
                                    output_buffer = lines[-1]
                                _append_output("\n".join(complete_lines))
                            elif process.poll() is not None:
                                break
                    else:
                        time.sleep(1)

                    if process.poll() is not None:
                        break

                    elapsed = int(time.monotonic() - start)
                    if elapsed // 15 > last_heartbeat:
                        last_heartbeat = elapsed // 15
                        update_status(f"  ⏳ {heartbeat_label} ({elapsed}s elapsed)")

                    if elapsed > install_timeout_seconds:
                        process.kill()
                        return False, f"Exceeded {install_timeout_seconds}s limit"

                if output_buffer.strip():
                    _append_output(output_buffer)

                returncode = process.wait()
                if returncode == 0:
                    return True, ""
                return False, f"Command exited with code {returncode}"
            finally:
                if process.stdout:
                    process.stdout.close()

        try:
            # 1. Create data directories
            update_status("📁 Creating data directories...")
            for d in [
                "data/threads",
                "data/tasks",
                "data/specs",
                "data/explorations",
                "data/registry",
                "data/logs",
                "data/sessions",
                "data/workflows",
                "data/mentions",
                "data/memory",
                "data/index",
            ]:
                (project_dir / d).mkdir(parents=True, exist_ok=True)
            update_status("  ✅ Data directories created")

            # 2. Write .env
            update_status("📝 Creating .env file...")
            env_content = generate_env_file(state)
            (project_dir / ".env").write_text(env_content)
            update_status("  ✅ .env file created")

            # 3. Write ultrawork.yaml
            update_status("📝 Creating ultrawork.yaml...")
            yaml_content = generate_ultrawork_yaml(state)
            (project_dir / "ultrawork.yaml").write_text(yaml_content)
            update_status("  ✅ ultrawork.yaml created")

            # 4. Write .mcp.json
            update_status("📝 Creating .mcp.json...")
            mcp_config = generate_mcp_json(state)
            (project_dir / ".mcp.json").write_text(
                json.dumps(mcp_config, indent=2, ensure_ascii=False)
            )
            update_status("  ✅ .mcp.json created")

            # 5. Update CLAUDE.md if needed
            update_status("📝 Checking CLAUDE.md update...")
            update_claude_md_for_tokens(project_dir, state)
            update_status("  ✅ CLAUDE.md verified")

            # 6. Install dependencies
            update_status("📦 Installing dependencies...")
            ok, err = run_with_progress(
                ["uv", "sync"],
                cwd=project_dir,
                heartbeat_label="Installing Python dependencies...",
            )
            if ok:
                update_status("  ✅ Python dependencies installed")
            else:
                update_status(f"  ⚠️ Dependency installation warning: {err}")

            # 7. Install selected MCPs
            for mcp_id in state.mcps_to_install:
                defn = MCP_DEFINITIONS.get(mcp_id, {})
                install_cmd = defn.get("install_cmd")
                if install_cmd:
                    update_status(f"📦 Installing {defn.get('name', mcp_id)}...")
                    ok, err = run_with_progress(
                        shlex.split(install_cmd),
                        heartbeat_label=f"Installing {defn.get('name', mcp_id)}...",
                    )
                    if ok:
                        update_status(f"  ✅ {defn.get('name', mcp_id)} installed")
                    else:
                        update_status(f"  ⚠️ {defn.get('name', mcp_id)} installation failed: {err}")

            update_status("\n🎉 Setup complete! You can now start the dashboard.")
            self.app.call_from_thread(self._enable_dashboard)

        except Exception as e:
            update_status(f"\n❌ Error occurred: {e}")

    def _enable_dashboard(self) -> None:
        self.query_one("#btn-dashboard", Button).disabled = False
        self.query_one("#btn-apply", Button).disabled = True
        # Save final state (keep for reconfiguration)
        app = self.app
        if isinstance(app, SetupWizardApp):
            app.state.last_completed_step = 7  # Mark as fully complete
            app.state.save()

    def launch_dashboard(self) -> None:
        import webbrowser
        import time

        app = self.app
        if not isinstance(app, SetupWizardApp):
            return

        state = app.state
        dashboard_url = f"http://localhost:{state.dashboard_port}"

        # Start daemon in background
        try:
            subprocess.Popen(
                ["uv", "run", "python", "-m", "ultrawork.slack.sdk_poller", "--agentic"],
                cwd=str(state.project_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            daemon_started = True
        except Exception:
            daemon_started = False

        # Start dashboard in background
        try:
            subprocess.Popen(
                ["uv", "run", "ultrawork", "dashboard", "--port", str(state.dashboard_port)],
                cwd=str(state.project_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # Wait a moment for server to start
            time.sleep(1)
            # Open browser automatically
            webbrowser.open(dashboard_url)
        except Exception:
            pass

        # Show completion message and exit
        if daemon_started:
            self.app.exit(
                message=(
                    "\n"
                    "╔══════════════════════════════════════════════════════════╗\n"
                    "║  🚀 Ultraworker has started!                             ║\n"
                    "╠══════════════════════════════════════════════════════════╣\n"
                    f"║  📊 Dashboard: {dashboard_url:<40}║\n"
                    "║  🤖 Slack daemon: Running in background                  ║\n"
                    "╠══════════════════════════════════════════════════════════╣\n"
                    "║  Stop: uv run ultrawork daemon:stop                      ║\n"
                    "║  Status: uv run ultrawork poll:status                    ║\n"
                    "╚══════════════════════════════════════════════════════════╝\n"
                )
            )
        else:
            self.app.exit(message="Setup complete!")


WIZARD_CSS = """
Screen {
    background: $surface;
}

.step-title {
    text-style: bold;
    color: $accent;
    padding: 1 2;
    text-align: center;
    width: 100%;
}

.guide-text {
    color: $text-muted;
    padding: 0 2 1 2;
}

.script-row {
    height: auto;
    padding: 0 2;
    margin-bottom: 1;
}

.script-text {
    color: $text;
    background: $surface-darken-1;
    padding: 0 1;
    width: 1fr;
}

#btn-copy-script {
    min-width: 10;
    margin-left: 1;
}

#copy-status {
    color: $success;
    padding: 0 2;
    height: auto;
}

.button-row {
    padding: 1 2;
    height: auto;
    align: center middle;
}

.button-row Button {
    margin: 0 1;
}

#permission-warning {
    color: $warning;
    padding: 1 2;
}

VerticalScroll {
    padding: 1 2;
}

Markdown {
    padding: 1 2;
}
"""


class SetupWizardApp(App):
    """Ultraworker Setup Wizard TUI Application."""

    TITLE = "Ultraworker Setup Wizard"
    CSS = WIZARD_CSS
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
    ]

    def __init__(self, project_dir: Path | None = None) -> None:
        super().__init__()
        # Load existing state if available
        self.state = SetupState.load(project_dir or Path.cwd())
        self.current_step = 0
        self.screens_list: list[type[Screen]] = [
            WelcomeScreen,
            Step0LanguageSelect,
            Step1ClaudeCheck,
            Step2SlackTokens,
            Step3BasicSettings,
            Step4MCPInstall,
            Step5Channels,
            Step6Tutorial,
            Step7Finish,
        ]

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())

    def action_next_step(self) -> None:
        # Save state before moving to next step
        self.state.last_completed_step = self.current_step
        self.state.save()

        self.current_step += 1
        if self.current_step < len(self.screens_list):
            self.switch_screen(self.screens_list[self.current_step]())

    def action_prev_step(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            self.switch_screen(self.screens_list[self.current_step]())

    def mark_setup_complete(self) -> None:
        """Called when setup is fully complete to clear saved state."""
        self.state.clear_saved_state()


def run_setup(project_dir: Path | None = None) -> None:
    """Run the setup wizard."""
    app = SetupWizardApp(project_dir=project_dir)
    app.run()
