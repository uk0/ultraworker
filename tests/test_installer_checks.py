"""Tests for installer checks module."""

from ultrawork.installer.checks import (
    SetupState,
    generate_env_file,
    generate_mcp_json,
    generate_ultrawork_yaml,
    validate_slack_bot_token,
    validate_slack_cookie,
    validate_slack_personal_token,
)


class TestSlackTokenValidation:
    def test_valid_bot_token(self) -> None:
        result = validate_slack_bot_token("xoxb-123-456-abc")
        assert result.ok is True

    def test_invalid_bot_token(self) -> None:
        result = validate_slack_bot_token("xoxc-123")
        assert result.ok is False

    def test_empty_bot_token(self) -> None:
        result = validate_slack_bot_token("")
        assert result.ok is False

    def test_valid_personal_token_xoxc(self) -> None:
        result = validate_slack_personal_token("xoxc-123-abc")
        assert result.ok is True

    def test_valid_personal_token_xoxp(self) -> None:
        result = validate_slack_personal_token("xoxp-123-abc")
        assert result.ok is True

    def test_invalid_personal_token(self) -> None:
        result = validate_slack_personal_token("xoxb-123")
        assert result.ok is False

    def test_valid_cookie(self) -> None:
        result = validate_slack_cookie("xoxd-abc123")
        assert result.ok is True

    def test_invalid_cookie(self) -> None:
        result = validate_slack_cookie("invalid-cookie")
        assert result.ok is False

    def test_empty_cookie(self) -> None:
        result = validate_slack_cookie("")
        assert result.ok is False


class TestSetupState:
    def test_default_state(self) -> None:
        state = SetupState()
        assert state.trigger_mode == "mention"
        assert state.permission_mode == "default"
        assert state.dashboard_port == 7878

    def test_env_vars_bot_only(self) -> None:
        state = SetupState(slack_bot_token="xoxb-123")
        env = state.get_env_vars()
        assert "SLACK_BOT_TOKEN" in env
        assert env["SLACK_BOT_TOKEN"] == "xoxb-123"
        assert "SLACK_TOKEN" not in env

    def test_env_vars_personal_only(self) -> None:
        state = SetupState(
            slack_personal_token="xoxc-123",
            slack_personal_cookie="xoxd-456",
        )
        env = state.get_env_vars()
        assert "SLACK_TOKEN" in env
        assert "SLACK_COOKIE" in env
        assert "SLACK_BOT_TOKEN" not in env

    def test_env_vars_both(self) -> None:
        state = SetupState(
            slack_bot_token="xoxb-123",
            slack_personal_token="xoxc-456",
        )
        env = state.get_env_vars()
        assert "SLACK_BOT_TOKEN" in env
        assert "SLACK_TOKEN" in env

    def test_env_vars_include_memory_search_bin_when_selected(self) -> None:
        state = SetupState(mcps_to_install=["memory-search"])
        env = state.get_env_vars()
        assert "MEMORY_SEARCH_BIN" in env
        assert env["MEMORY_SEARCH_BIN"].endswith("/memory-search/target/release/memory-search")


class TestGenerateEnvFile:
    def test_bot_token_env(self) -> None:
        state = SetupState(slack_bot_token="xoxb-test-token")
        content = generate_env_file(state)
        assert "SLACK_BOT_TOKEN=xoxb-test-token" in content

    def test_personal_token_env(self) -> None:
        state = SetupState(
            slack_personal_token="xoxc-test",
            slack_personal_cookie="xoxd-test",
        )
        content = generate_env_file(state)
        assert "SLACK_TOKEN=xoxc-test" in content
        assert "SLACK_COOKIE=xoxd-test" in content


class TestGenerateUltraworkYaml:
    def test_mention_mode(self) -> None:
        state = SetupState(bot_user_id="U123ABC", trigger_mode="mention")
        content = generate_ultrawork_yaml(state)
        assert "bot_user_id: U123ABC" in content
        assert 'trigger_pattern: "<@U123ABC>"' in content
        assert "memory:" in content
        assert 'search_binary: "' in content

    def test_keyword_mode(self) -> None:
        state = SetupState(
            bot_user_id="U123ABC",
            trigger_mode="keyword",
            custom_keyword="!ultra",
        )
        content = generate_ultrawork_yaml(state)
        assert 'trigger_pattern: "!ultra"' in content
        assert "auto_index_on_save: true" in content


class TestGenerateMcpJson:
    def test_bot_only(self) -> None:
        state = SetupState(slack_bot_token="xoxb-123")
        config = generate_mcp_json(state)
        assert "slack-bot-mcp" in config["mcpServers"]
        assert "slack" not in config["mcpServers"]

    def test_personal_only(self) -> None:
        state = SetupState(slack_personal_token="xoxc-123")
        config = generate_mcp_json(state)
        assert "slack" in config["mcpServers"]
        assert "slack-bot-mcp" not in config["mcpServers"]

    def test_both_tokens(self) -> None:
        state = SetupState(
            slack_bot_token="xoxb-123",
            slack_personal_token="xoxc-456",
        )
        config = generate_mcp_json(state)
        assert "slack" in config["mcpServers"]
        assert "slack-bot-mcp" in config["mcpServers"]

    def test_additional_mcps(self) -> None:
        state = SetupState(
            slack_bot_token="xoxb-123",
            mcps_to_install=["playwright", "context7"],
        )
        config = generate_mcp_json(state)
        assert "playwright" in config["mcpServers"]
        assert "context7" in config["mcpServers"]

    def test_memory_search_mcp(self) -> None:
        state = SetupState(mcps_to_install=["memory-search"])
        config = generate_mcp_json(state)
        assert "memory-search" in config["mcpServers"]
        entry = config["mcpServers"]["memory-search"]
        assert entry["command"].endswith("/memory-search/target/release/memory-search")
        assert entry["args"][0] == "serve"
        assert "--data-dir" in entry["args"]

    def test_agent_browser_is_install_only(self) -> None:
        state = SetupState(mcps_to_install=["agent-browser"])
        config = generate_mcp_json(state)
        assert "agent-browser" not in config["mcpServers"]

    def test_no_tokens(self) -> None:
        state = SetupState()
        config = generate_mcp_json(state)
        assert len(config["mcpServers"]) == 0
