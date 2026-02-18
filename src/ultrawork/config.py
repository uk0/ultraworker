"""Configuration management for Ultrawork."""

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class SlackConfig(BaseModel):
    """Slack integration configuration."""

    bot_user_id: str = ""  # Set via environment or config file
    default_channel: str = ""
    trigger_pattern: str = ""  # Custom trigger pattern

    @field_validator("bot_user_id", "default_channel", "trigger_pattern", mode="before")
    @classmethod
    def convert_none_to_empty(cls, v: str | None) -> str:
        """Convert None to empty string."""
        return v if v is not None else ""


class PollingConfig(BaseModel):
    """Polling configuration for real-time Slack monitoring."""

    enabled: bool = False
    poll_interval_seconds: int = 60
    max_messages_per_poll: int = 50
    max_thread_history: int = 100  # Max messages to fetch per thread
    explore_depth: int = 2  # How many levels of context to explore
    max_processed_cache: int = 10000  # Max message IDs to remember
    max_consecutive_errors: int = 5  # Stop polling after N consecutive errors


class ResponseConfig(BaseModel):
    """Response generation configuration."""

    auto_respond: bool = True  # Enable hybrid auto-response
    confidence_threshold: float = 0.8  # Minimum confidence for auto-send
    auto_types: list[str] = ["acknowledge", "simple_query"]  # Types to auto-send
    manual_types: list[str] = ["action", "complex", "defer"]  # Types requiring review

    def __init__(self, **data):
        # Handle None values by converting to empty lists
        if data.get("auto_types") is None:
            data["auto_types"] = []
        if data.get("manual_types") is None:
            data["manual_types"] = []
        super().__init__(**data)


class ExecutorConfig(BaseModel):
    """Executor configuration for Claude/Codex CLI."""

    claude_command: str = "claude"
    codex_command: str = "codex"
    default_executor: str = "claude"  # "claude" or "codex"
    timeout_seconds: int = 300
    agentic_timeout_seconds: int = Field(
        default_factory=lambda: int(os.environ.get("ULTRAWORK_AGENTIC_TIMEOUT", "1800"))
    )  # 30 minutes default for agentic tasks


class WorkflowConfig(BaseModel):
    """Workflow configuration."""

    auto_approve_simple_tasks: bool = False
    require_tech_spec_for_code: bool = True
    default_workflow_type: str = "full"  # "full" or "simple"


class CronjobConfig(BaseModel):
    """Cron job scheduler configuration."""

    enabled: bool = True  # Enable cron job scheduler in daemon
    check_interval_seconds: int = 60  # How often to check for due jobs
    max_error_pause: int = 3  # Auto-pause job after N consecutive failures


# Supported languages for the system
SUPPORTED_LANGUAGES = {
    "en": "English",
    "ko": "한국어",
    "ja": "日本語",
    "zh": "中文",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "pt": "Português",
}


class LanguageConfig(BaseModel):
    """Language configuration for all system outputs."""

    default: str = "en"  # Language code or custom language string

    @field_validator("default", mode="before")
    @classmethod
    def validate_language(cls, v: str | None) -> str:
        """Validate language code. Accepts both predefined codes and custom values."""
        if v is None:
            return "en"
        v = v.strip()
        if not v:
            return "en"
        # Accept predefined codes (case-insensitive) and any custom value
        lower = v.lower()
        if lower in SUPPORTED_LANGUAGES:
            return lower
        return v


class UltraworkConfig(BaseModel):
    """Main configuration for Ultrawork."""

    data_dir: Path = Field(default=Path("data"))
    slack: SlackConfig = Field(default_factory=SlackConfig)
    polling: PollingConfig = Field(default_factory=PollingConfig)
    response: ResponseConfig = Field(default_factory=ResponseConfig)
    executor: ExecutorConfig = Field(default_factory=ExecutorConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    cronjob: CronjobConfig = Field(default_factory=CronjobConfig)
    language: LanguageConfig = Field(default_factory=LanguageConfig)

    @classmethod
    def load(cls, config_path: Path | None = None) -> "UltraworkConfig":
        """Load configuration from file or use defaults.

        If no config_path is provided, looks for ultrawork.yaml in:
        1. Current working directory
        2. Parent directories (up to 3 levels)
        """
        import yaml

        def _resolve_data_dir(data: dict, path: Path | None) -> dict:
            data_dir = data.get("data_dir")
            if not data_dir:
                return data
            data_dir_path = Path(data_dir)
            if data_dir_path.is_absolute():
                return data
            if path:
                data["data_dir"] = str((path.parent / data_dir_path).resolve())
            return data

        def _load_from(path: Path) -> "UltraworkConfig":
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            data = _resolve_data_dir(data, path)
            return cls(**data)

        # If path provided, use it
        if config_path and config_path.exists():
            return _load_from(config_path)

        # Auto-discover config file
        search_paths = []
        for root in [Path.cwd(), *Path.cwd().parents[:3]]:
            search_paths.append(root / "ultrawork.yaml")
            search_paths.append(root / ".ultrawork.yaml")

        module_root = Path(__file__).resolve().parents[2]
        search_paths.append(module_root / "ultrawork.yaml")
        search_paths.append(module_root / ".ultrawork.yaml")

        for path in search_paths:
            if path.exists():
                return _load_from(path)

        return cls()

    def save(self, config_path: Path) -> None:
        """Save configuration to file."""
        import yaml

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            yaml.dump(self.model_dump(mode="json"), allow_unicode=True),
            encoding="utf-8",
        )


# Global config instance
_config: UltraworkConfig | None = None


def find_config_path(start: Path | None = None) -> Path | None:
    """Locate ultrawork.yaml by walking up from start and module root."""
    start = start or Path.cwd()
    for root in [start, *start.parents[:3]]:
        for name in ("ultrawork.yaml", ".ultrawork.yaml"):
            candidate = root / name
            if candidate.exists():
                return candidate

    module_root = Path(__file__).resolve().parents[2]
    for name in ("ultrawork.yaml", ".ultrawork.yaml"):
        candidate = module_root / name
        if candidate.exists():
            return candidate

    return None


def get_config() -> UltraworkConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = UltraworkConfig.load()
    return _config


def set_config(config: UltraworkConfig) -> None:
    """Set the global configuration instance."""
    global _config
    _config = config
