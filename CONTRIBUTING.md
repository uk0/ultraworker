# Contributing to Ultraworker

Thank you for your interest in contributing to Ultraworker! This document provides guidelines and instructions for contributing.

## Getting Started

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for package management
- [Claude Code](https://claude.ai/claude-code) CLI for skill execution

### Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/DolbonIn/ultraworker.git
   cd ultraworker
   ```

2. Install dependencies:
   ```bash
   make dev
   ```

3. Copy example configuration files:
   ```bash
   cp .env.example .env
   cp .mcp.json.example .mcp.json
   ```

4. Configure your Slack tokens in `.mcp.json`

## Development Workflow

### Code Style

We use `ruff` for linting and formatting. Before submitting:

```bash
make format   # Format code
make check    # Run linters and type checkers
make test     # Run tests
```

### Running Tests

```bash
make test              # Run all tests
uv run pytest -v       # Verbose output
uv run pytest -k name  # Run specific tests
```

### Adding New Skills

1. Create a new directory under `.claude/skills/your-skill-name/`
2. Add `SKILL.md` with skill definition following the existing format
3. Register the skill in the configuration if needed
4. Add tests for your skill

### Adding New Agents

1. Create a new file under `.claude/agents/your-agent.md`
2. Follow the agent template structure
3. Document tools used and execution steps

## Submitting Changes

### Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Make your changes with clear, atomic commits
4. Ensure all tests pass: `make check && make test`
5. Push to your fork and create a Pull Request

### Commit Messages

Follow conventional commits:
- `feat:` - New features
- `fix:` - Bug fixes
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

Example:
```
feat: add retry logic to Slack polling

- Add exponential backoff on rate limits
- Configure max retry attempts via settings
- Log retry attempts for debugging
```

### Code Review

All submissions require review. We use GitHub pull requests for this purpose.

## Reporting Issues

### Bug Reports

Include:
- Ultraworker version
- Python version
- Steps to reproduce
- Expected vs actual behavior
- Error messages and logs

### Feature Requests

- Describe the use case
- Explain how it fits the project goals
- Consider implementation approach

## Community

- Be respectful and inclusive
- Follow the [Contributor Covenant](https://www.contributor-covenant.org/)
- Help others when you can

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
