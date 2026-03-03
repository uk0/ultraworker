"""Tests for security/redaction utilities."""

from ultrawork.memory.redact import generate_dedupe_key, redact_secrets


class TestRedactSecrets:
    def test_slack_user_token(self) -> None:
        text = "Token: xoxc-1234567890-abcdef"
        result = redact_secrets(text)
        assert "xoxc-" not in result
        assert "[REDACTED:slack-user-token]" in result

    def test_slack_bot_token(self) -> None:
        text = "Bot: xoxb-1234567890-abcdef"
        result = redact_secrets(text)
        assert "xoxb-" not in result
        assert "[REDACTED:slack-bot-token]" in result

    def test_anthropic_key(self) -> None:
        text = "Key: sk-ant-abc123def456-ghi789"
        result = redact_secrets(text)
        assert "sk-ant-" not in result
        assert "[REDACTED:anthropic-api-key]" in result

    def test_aws_key(self) -> None:
        text = "AWS: AKIAIOSFODNN7EXAMPLE"
        result = redact_secrets(text)
        assert "AKIA" not in result
        assert "[REDACTED:aws-access-key]" in result

    def test_github_pat(self) -> None:
        text = "GH: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
        result = redact_secrets(text)
        assert "ghp_" not in result
        assert "[REDACTED:github-pat]" in result

    def test_no_secrets(self) -> None:
        text = "Just normal text without any secrets"
        assert redact_secrets(text) == text

    def test_multiple_secrets(self) -> None:
        text = "Tokens: xoxc-abc123 and xoxb-def456"
        result = redact_secrets(text)
        assert "xoxc-" not in result
        assert "xoxb-" not in result


class TestGenerateDedupeKey:
    def test_deterministic(self) -> None:
        key1 = generate_dedupe_key("hello world", "step1", ["uri1"])
        key2 = generate_dedupe_key("hello world", "step1", ["uri1"])
        assert key1 == key2

    def test_different_content(self) -> None:
        key1 = generate_dedupe_key("hello", "step1", ["uri1"])
        key2 = generate_dedupe_key("world", "step1", ["uri1"])
        assert key1 != key2

    def test_case_insensitive(self) -> None:
        key1 = generate_dedupe_key("Hello World", "Step1", ["URI1"])
        key2 = generate_dedupe_key("hello world", "step1", ["uri1"])
        assert key1 == key2

    def test_whitespace_normalized(self) -> None:
        key1 = generate_dedupe_key("hello  world", "step", [])
        key2 = generate_dedupe_key("hello world", "step", [])
        assert key1 == key2

    def test_uri_order_independent(self) -> None:
        key1 = generate_dedupe_key("content", "step", ["uri1", "uri2"])
        key2 = generate_dedupe_key("content", "step", ["uri2", "uri1"])
        assert key1 == key2

    def test_returns_hex_string(self) -> None:
        key = generate_dedupe_key("test", "", [])
        assert len(key) == 64  # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in key)
