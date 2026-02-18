/**
 * Ultraworker Dashboard - Demo Mode with Mock Data
 * This version replaces all live API calls with static mock data
 * to demonstrate the dashboard UI without a running backend.
 */

const THREAD_PAGE_SIZE = 5;
const THREAD_REFRESH_MS = 15000;
const TOOL_PREVIEW_LIMIT = 360;
const INITIAL_EVENT_LIMIT = 120;
const OLDER_EVENT_LIMIT = 120;
const RENDER_CHUNK_SIZE = 28;

// ===== MOCK DATA =====

const MOCK_THREADS = [
  {
    thread_id: "thread-001",
    channel_id: "C06ABC123",
    channel_name: "eng-common",
    thread_ts: "1706500000.000000",
    title: "@ultraworker Investigate login latency spike in auth-service",
    latest_text: "We've been seeing p99 latency above 2s for the /auth/login endpoint since the last deployment. Can you investigate and fix this?",
    status: "completed",
    request_count: 1,
    session_count: 3,
    live_session_count: 0,
    latest_session_id: "sess-a1b2c3d4",
    updated_at: new Date(Date.now() - 12 * 60000).toISOString(),
    created_at: new Date(Date.now() - 180 * 60000).toISOString(),
  },
  {
    thread_id: "thread-002",
    channel_id: "C06DEF456",
    channel_name: "product-storm",
    thread_ts: "1706510000.000000",
    title: "@ultraworker Add dark mode toggle to user settings",
    latest_text: "Users have been requesting dark mode support. Let's add a toggle in the settings page that persists the preference.",
    status: "active",
    request_count: 1,
    session_count: 2,
    live_session_count: 1,
    latest_session_id: "sess-e5f6g7h8",
    updated_at: new Date(Date.now() - 3 * 60000).toISOString(),
    created_at: new Date(Date.now() - 90 * 60000).toISOString(),
  },
  {
    thread_id: "thread-003",
    channel_id: "C06GHI789",
    channel_name: "research-common",
    thread_ts: "1706520000.000000",
    title: "@ultraworker Set up RAG pipeline for internal knowledge base",
    latest_text: "We need a retrieval-augmented generation pipeline that indexes our Confluence docs and provides accurate answers.",
    status: "waiting",
    request_count: 1,
    session_count: 1,
    live_session_count: 0,
    latest_session_id: "sess-i9j0k1l2",
    updated_at: new Date(Date.now() - 45 * 60000).toISOString(),
    created_at: new Date(Date.now() - 240 * 60000).toISOString(),
  },
];

const MOCK_SESSIONS = {
  "thread-001": [
    {
      session_id: "sess-a1b2c3d4",
      status: "completed",
      request_preview: "Investigate login latency spike",
      summary: "Identified N+1 query in session validation, applied batch query optimization",
      created_at: new Date(Date.now() - 180 * 60000).toISOString(),
      updated_at: new Date(Date.now() - 12 * 60000).toISOString(),
      event_count: 24,
      event_counts: { thinking: 4, tool_call: 14, tool_result: 14, output: 2 },
    },
    {
      session_id: "sess-m3n4o5p6",
      status: "completed",
      request_preview: "Write tech spec for auth optimization",
      summary: "Generated detailed tech spec with implementation plan for batch query optimization",
      created_at: new Date(Date.now() - 120 * 60000).toISOString(),
      updated_at: new Date(Date.now() - 90 * 60000).toISOString(),
      event_count: 18,
      event_counts: { thinking: 3, tool_call: 10, tool_result: 10, output: 1 },
    },
    {
      session_id: "sess-q7r8s9t0",
      status: "completed",
      request_preview: "Generate final report",
      summary: "Final report generated with test results showing p99 latency reduced to 180ms",
      created_at: new Date(Date.now() - 30 * 60000).toISOString(),
      updated_at: new Date(Date.now() - 12 * 60000).toISOString(),
      event_count: 12,
      event_counts: { thinking: 2, tool_call: 6, tool_result: 6, output: 1 },
    },
  ],
  "thread-002": [
    {
      session_id: "sess-e5f6g7h8",
      status: "active",
      request_preview: "Add dark mode toggle to settings",
      summary: "Implementing dark mode CSS variables and toggle component",
      created_at: new Date(Date.now() - 90 * 60000).toISOString(),
      updated_at: new Date(Date.now() - 3 * 60000).toISOString(),
      event_count: 16,
      event_counts: { thinking: 3, tool_call: 8, tool_result: 8, output: 0 },
    },
    {
      session_id: "sess-u1v2w3x4",
      status: "completed",
      request_preview: "Context exploration for dark mode",
      summary: "Explored existing theme system and user preferences storage",
      created_at: new Date(Date.now() - 88 * 60000).toISOString(),
      updated_at: new Date(Date.now() - 60 * 60000).toISOString(),
      event_count: 10,
      event_counts: { thinking: 2, tool_call: 5, tool_result: 5, output: 1 },
    },
  ],
  "thread-003": [
    {
      session_id: "sess-i9j0k1l2",
      status: "waiting",
      request_preview: "Set up RAG pipeline",
      summary: "Tech spec drafted, waiting for approval",
      created_at: new Date(Date.now() - 240 * 60000).toISOString(),
      updated_at: new Date(Date.now() - 45 * 60000).toISOString(),
      event_count: 14,
      event_counts: { thinking: 3, tool_call: 7, tool_result: 7, output: 1 },
    },
  ],
};

function generateMockEvents(sessionId) {
  const now = Date.now();

  const eventSets = {
    "sess-a1b2c3d4": [
      {
        event_id: "sess-a1b2c3d4:command",
        kind: "user_command",
        seq: 1,
        status: "completed",
        preview: "Investigate login latency spike in auth-service. We've been seeing p99 latency above 2s for /auth/login since the last deployment.",
        ts: new Date(now - 180 * 60000).toISOString(),
        raw: { type: "user_input" },
      },
      {
        event_id: "sess-a1b2c3d4:obs-1",
        kind: "assistant_observation",
        seq: 2,
        status: "completed",
        preview: "Processing started. I'll investigate the auth-service login latency issue by examining recent changes, profiling the endpoint, and analyzing database queries.",
        ts: new Date(now - 179 * 60000).toISOString(),
        raw: { type: "processing_started" },
      },
      {
        event_id: "sess-a1b2c3d4:think-1",
        kind: "assistant_thinking",
        seq: 3,
        status: "completed",
        preview: "The latency spike correlates with the last deployment. I need to check the git log for recent changes to the auth module, then profile the endpoint to identify the bottleneck.",
        ts: new Date(now - 178 * 60000).toISOString(),
      },
      {
        event_id: "tool-grep-1",
        kind: "tool_call",
        seq: 4,
        status: "completed",
        title: "Grep",
        tool_use_id: "tool-grep-1",
        preview: "pattern: \"session.*validate|login.*query\", path: src/auth/",
        ts: new Date(now - 177 * 60000).toISOString(),
        raw: { input: { pattern: "session.*validate|login.*query", path: "src/auth/" } },
      },
      {
        event_id: "tool-grep-1-result",
        kind: "tool_result",
        seq: 5,
        status: "completed",
        title: "Grep",
        tool_use_id: "tool-grep-1",
        parent_event_id: "tool-grep-1",
        preview: "Found 8 matches in 3 files",
        ts: new Date(now - 176 * 60000).toISOString(),
        raw: { content: "src/auth/session.py:42: def validate_session(self, session_id):\nsrc/auth/session.py:55:     result = db.query(Session).filter_by(id=session_id).first()\nsrc/auth/session.py:67:     permissions = db.query(Permission).filter_by(user_id=user.id).all()\nsrc/auth/login.py:23: async def login_handler(request):\nsrc/auth/login.py:38:     session = await validate_session(token)\nsrc/auth/login.py:45:     roles = await fetch_user_roles(user.id)\nsrc/auth/models.py:12: class Session(Base):\nsrc/auth/models.py:28: class Permission(Base):" },
      },
      {
        event_id: "tool-read-1",
        kind: "tool_call",
        seq: 6,
        status: "completed",
        title: "Read",
        tool_use_id: "tool-read-1",
        preview: "file_path: src/auth/session.py",
        ts: new Date(now - 175 * 60000).toISOString(),
        raw: { input: { file_path: "src/auth/session.py" } },
      },
      {
        event_id: "tool-read-1-result",
        kind: "tool_result",
        seq: 7,
        status: "completed",
        title: "Read",
        tool_use_id: "tool-read-1",
        parent_event_id: "tool-read-1",
        preview: "Read 89 lines from src/auth/session.py",
        ts: new Date(now - 174 * 60000).toISOString(),
        raw: { content: "class SessionValidator:\n    def validate_session(self, session_id):\n        session = db.query(Session).filter_by(id=session_id).first()\n        if not session:\n            raise InvalidSession()\n        user = db.query(User).filter_by(id=session.user_id).first()\n        # N+1 QUERY: fetching permissions one-by-one for each role\n        for role in user.roles:\n            permissions = db.query(Permission).filter_by(role_id=role.id).all()\n            session.permissions.extend(permissions)\n        return session" },
      },
      {
        event_id: "sess-a1b2c3d4:think-2",
        kind: "assistant_thinking",
        seq: 8,
        status: "completed",
        preview: "Found the issue! There's an N+1 query pattern in SessionValidator.validate_session(). For each role, it issues a separate DB query for permissions. With users having 5-10 roles, that's 5-10 extra queries per login. I need to refactor this to use a single batch query with IN clause.",
        ts: new Date(now - 173 * 60000).toISOString(),
      },
      {
        event_id: "tool-bash-1",
        kind: "tool_call",
        seq: 9,
        status: "completed",
        title: "Bash",
        tool_use_id: "tool-bash-1",
        preview: "git log --oneline -5 -- src/auth/session.py",
        ts: new Date(now - 172 * 60000).toISOString(),
        raw: { input: { command: "git log --oneline -5 -- src/auth/session.py" } },
      },
      {
        event_id: "tool-bash-1-result",
        kind: "tool_result",
        seq: 10,
        status: "completed",
        title: "Bash",
        tool_use_id: "tool-bash-1",
        parent_event_id: "tool-bash-1",
        ts: new Date(now - 171 * 60000).toISOString(),
        raw: { content: "a3f2d1c feat: add per-role permission validation (3 days ago)\nb8e4a2d refactor: extract session validator class (1 week ago)\nc7f3b1e fix: handle expired sessions gracefully (2 weeks ago)\nd6e2c0f feat: add session metadata tracking (3 weeks ago)\ne5d1b9a initial auth module setup (1 month ago)" },
      },
      {
        event_id: "tool-edit-1",
        kind: "tool_call",
        seq: 11,
        status: "completed",
        title: "Edit",
        tool_use_id: "tool-edit-1",
        preview: "file_path: src/auth/session.py - Replace N+1 query with batch query",
        ts: new Date(now - 170 * 60000).toISOString(),
        raw: { input: { file_path: "src/auth/session.py", old_string: "for role in user.roles:\n            permissions = db.query(Permission).filter_by(role_id=role.id).all()", new_string: "role_ids = [role.id for role in user.roles]\npermissions = db.query(Permission).filter(Permission.role_id.in_(role_ids)).all()" } },
      },
      {
        event_id: "tool-edit-1-result",
        kind: "tool_result",
        seq: 12,
        status: "completed",
        title: "Edit",
        tool_use_id: "tool-edit-1",
        parent_event_id: "tool-edit-1",
        ts: new Date(now - 169 * 60000).toISOString(),
        raw: { content: "Successfully edited src/auth/session.py" },
      },
      {
        event_id: "tool-bash-2",
        kind: "tool_call",
        seq: 13,
        status: "completed",
        title: "Bash",
        tool_use_id: "tool-bash-2",
        preview: "uv run pytest tests/auth/ -v --tb=short",
        ts: new Date(now - 168 * 60000).toISOString(),
        raw: { input: { command: "uv run pytest tests/auth/ -v --tb=short" } },
      },
      {
        event_id: "tool-bash-2-result",
        kind: "tool_result",
        seq: 14,
        status: "completed",
        title: "Bash",
        tool_use_id: "tool-bash-2",
        parent_event_id: "tool-bash-2",
        ts: new Date(now - 167 * 60000).toISOString(),
        raw: { content: "tests/auth/test_session.py::test_validate_session PASSED\ntests/auth/test_session.py::test_validate_expired_session PASSED\ntests/auth/test_session.py::test_validate_permissions_batch PASSED\ntests/auth/test_login.py::test_login_success PASSED\ntests/auth/test_login.py::test_login_invalid_token PASSED\ntests/auth/test_login.py::test_login_latency PASSED\n\n6 passed in 2.34s" },
      },
      {
        event_id: "sess-a1b2c3d4:think-3",
        kind: "assistant_thinking",
        seq: 15,
        status: "completed",
        preview: "All tests pass. The N+1 query has been replaced with a batch query using IN clause. This should reduce the number of DB round-trips from N to 1, bringing p99 latency well below the 2s threshold.",
        ts: new Date(now - 166 * 60000).toISOString(),
      },
      {
        event_id: "tool-slack-1",
        kind: "tool_call",
        seq: 16,
        status: "completed",
        title: "mcp__slack__slack_send_message",
        tool_use_id: "tool-slack-1",
        preview: "channel_id: C06ABC123, thread_ts: 1706500000.000000",
        ts: new Date(now - 165 * 60000).toISOString(),
        raw: { input: { channel_id: "C06ABC123", thread_ts: "1706500000.000000", text: "Investigation complete. Root cause: N+1 query in SessionValidator.validate_session(). Fix applied - replaced per-role permission queries with batch IN clause. All 6 tests passing. p99 latency expected to drop from 2s+ to ~180ms." } },
      },
      {
        event_id: "tool-slack-1-result",
        kind: "tool_result",
        seq: 17,
        status: "completed",
        title: "mcp__slack__slack_send_message",
        tool_use_id: "tool-slack-1",
        parent_event_id: "tool-slack-1",
        ts: new Date(now - 164 * 60000).toISOString(),
        raw: { content: "Message sent successfully to #eng-common" },
      },
      {
        event_id: "sess-a1b2c3d4:output-1",
        kind: "assistant_output",
        seq: 18,
        status: "completed",
        preview: "Investigation complete. Root cause identified as N+1 query pattern in session validation. Applied batch query optimization. All tests passing. Status update posted to Slack thread.",
        ts: new Date(now - 163 * 60000).toISOString(),
      },
    ],
    "sess-e5f6g7h8": [
      {
        event_id: "sess-e5f6g7h8:command",
        kind: "user_command",
        seq: 1,
        status: "completed",
        preview: "Add dark mode toggle to user settings page. The toggle should persist user preference and apply CSS variables for theming.",
        ts: new Date(now - 90 * 60000).toISOString(),
        raw: { type: "user_input" },
      },
      {
        event_id: "sess-e5f6g7h8:obs-1",
        kind: "assistant_observation",
        seq: 2,
        status: "completed",
        preview: "Processing started. I'll explore the existing theme system, create a dark mode toggle component, and set up CSS custom properties for theme switching.",
        ts: new Date(now - 89 * 60000).toISOString(),
        raw: { type: "processing_started" },
      },
      {
        event_id: "sess-e5f6g7h8:think-1",
        kind: "assistant_thinking",
        seq: 3,
        status: "completed",
        preview: "I need to first understand the existing component architecture and any theme-related code. Let me search for existing CSS variables and theme utilities.",
        ts: new Date(now - 88 * 60000).toISOString(),
      },
      {
        event_id: "tool-glob-1",
        kind: "tool_call",
        seq: 4,
        status: "completed",
        title: "Glob",
        tool_use_id: "tool-glob-1",
        preview: "pattern: **/*theme*.{ts,tsx,css}, path: src/",
        ts: new Date(now - 87 * 60000).toISOString(),
        raw: { input: { pattern: "**/*theme*.{ts,tsx,css}", path: "src/" } },
      },
      {
        event_id: "tool-glob-1-result",
        kind: "tool_result",
        seq: 5,
        status: "completed",
        title: "Glob",
        tool_use_id: "tool-glob-1",
        parent_event_id: "tool-glob-1",
        ts: new Date(now - 86 * 60000).toISOString(),
        raw: { content: "src/styles/theme.css\nsrc/components/ThemeProvider.tsx\nsrc/hooks/useTheme.ts\nsrc/utils/theme-constants.ts" },
      },
      {
        event_id: "tool-read-2",
        kind: "tool_call",
        seq: 6,
        status: "completed",
        title: "Read",
        tool_use_id: "tool-read-2",
        preview: "file_path: src/styles/theme.css",
        ts: new Date(now - 85 * 60000).toISOString(),
        raw: { input: { file_path: "src/styles/theme.css" } },
      },
      {
        event_id: "tool-read-2-result",
        kind: "tool_result",
        seq: 7,
        status: "completed",
        title: "Read",
        tool_use_id: "tool-read-2",
        parent_event_id: "tool-read-2",
        ts: new Date(now - 84 * 60000).toISOString(),
        raw: { content: ":root {\n  --bg-primary: #ffffff;\n  --bg-secondary: #f8fafc;\n  --text-primary: #0f172a;\n  --text-secondary: #64748b;\n  --border: #e2e8f0;\n  --brand: #4f46e5;\n}\n\n/* Dark mode variables not yet defined */" },
      },
      {
        event_id: "tool-todowrite-1",
        kind: "tool_call",
        seq: 8,
        status: "completed",
        title: "TodoWrite",
        tool_use_id: "tool-todowrite-1",
        preview: "Creating implementation checklist",
        ts: new Date(now - 83 * 60000).toISOString(),
        raw: { input: { todos: [
          { content: "Define dark mode CSS variables", status: "completed" },
          { content: "Create DarkModeToggle component", status: "in_progress" },
          { content: "Add localStorage persistence", status: "pending" },
          { content: "Update ThemeProvider context", status: "pending" },
          { content: "Run tests and verify", status: "pending" },
        ] } },
      },
      {
        event_id: "tool-todowrite-1-result",
        kind: "tool_result",
        seq: 9,
        status: "completed",
        title: "TodoWrite",
        tool_use_id: "tool-todowrite-1",
        parent_event_id: "tool-todowrite-1",
        ts: new Date(now - 82 * 60000).toISOString(),
        raw: { content: "- [x] Define dark mode CSS variables\n- [ ] Create DarkModeToggle component\n- [ ] Add localStorage persistence\n- [ ] Update ThemeProvider context\n- [ ] Run tests and verify" },
      },
      {
        event_id: "tool-edit-2",
        kind: "tool_call",
        seq: 10,
        status: "completed",
        title: "Edit",
        tool_use_id: "tool-edit-2",
        preview: "file_path: src/styles/theme.css - Add dark mode variables",
        ts: new Date(now - 80 * 60000).toISOString(),
        raw: { input: { file_path: "src/styles/theme.css" } },
      },
      {
        event_id: "tool-edit-2-result",
        kind: "tool_result",
        seq: 11,
        status: "completed",
        title: "Edit",
        tool_use_id: "tool-edit-2",
        parent_event_id: "tool-edit-2",
        ts: new Date(now - 79 * 60000).toISOString(),
        raw: { content: "Successfully edited src/styles/theme.css - Added [data-theme='dark'] variables" },
      },
      {
        event_id: "tool-write-1",
        kind: "tool_call",
        seq: 12,
        status: "completed",
        title: "Write",
        tool_use_id: "tool-write-1",
        preview: "file_path: src/components/DarkModeToggle.tsx",
        ts: new Date(now - 75 * 60000).toISOString(),
        raw: { input: { file_path: "src/components/DarkModeToggle.tsx" } },
      },
      {
        event_id: "tool-write-1-result",
        kind: "tool_result",
        seq: 13,
        status: "completed",
        title: "Write",
        tool_use_id: "tool-write-1",
        parent_event_id: "tool-write-1",
        ts: new Date(now - 74 * 60000).toISOString(),
        raw: { content: "Successfully wrote src/components/DarkModeToggle.tsx (42 lines)" },
      },
      {
        event_id: "sess-e5f6g7h8:think-2",
        kind: "assistant_thinking",
        seq: 14,
        status: "active",
        preview: "Dark mode CSS variables and toggle component are in place. Now I need to update the ThemeProvider to persist the preference in localStorage and integrate the toggle into the settings page.",
        ts: new Date(now - 10 * 60000).toISOString(),
      },
    ],
    "sess-i9j0k1l2": [
      {
        event_id: "sess-i9j0k1l2:command",
        kind: "user_command",
        seq: 1,
        status: "completed",
        preview: "Set up RAG pipeline for internal knowledge base. We need to index Confluence docs and provide accurate answers to team queries.",
        ts: new Date(now - 240 * 60000).toISOString(),
        raw: { type: "user_input" },
      },
      {
        event_id: "sess-i9j0k1l2:obs-1",
        kind: "assistant_observation",
        seq: 2,
        status: "completed",
        preview: "Processing started. I'll explore the current document infrastructure, design the RAG architecture, and create a tech spec for approval.",
        ts: new Date(now - 239 * 60000).toISOString(),
        raw: { type: "processing_started" },
      },
      {
        event_id: "sess-i9j0k1l2:think-1",
        kind: "assistant_thinking",
        seq: 3,
        status: "completed",
        preview: "This is a substantial feature. I need to understand the existing infrastructure, available embedding models, and vector store options before proposing a design.",
        ts: new Date(now - 238 * 60000).toISOString(),
      },
      {
        event_id: "tool-websearch-1",
        kind: "tool_call",
        seq: 4,
        status: "completed",
        title: "WebSearch",
        tool_use_id: "tool-websearch-1",
        preview: "query: RAG pipeline best practices 2026 production",
        ts: new Date(now - 237 * 60000).toISOString(),
        raw: { input: { query: "RAG pipeline best practices 2026 production" } },
      },
      {
        event_id: "tool-websearch-1-result",
        kind: "tool_result",
        seq: 5,
        status: "completed",
        title: "WebSearch",
        tool_use_id: "tool-websearch-1",
        parent_event_id: "tool-websearch-1",
        ts: new Date(now - 236 * 60000).toISOString(),
        raw: { content: "Found 12 results. Top recommendations: use hybrid search (sparse + dense), chunk documents at semantic boundaries, implement re-ranking with cross-encoders, use pgvector for vector storage in existing PostgreSQL infrastructure." },
      },
      {
        event_id: "tool-write-2",
        kind: "tool_call",
        seq: 6,
        status: "completed",
        title: "Write",
        tool_use_id: "tool-write-2",
        preview: "file_path: data/specs/TASK-2026-0219-001_spec.md",
        ts: new Date(now - 200 * 60000).toISOString(),
        raw: { input: { file_path: "data/specs/TASK-2026-0219-001_spec.md" } },
      },
      {
        event_id: "tool-write-2-result",
        kind: "tool_result",
        seq: 7,
        status: "completed",
        title: "Write",
        tool_use_id: "tool-write-2",
        parent_event_id: "tool-write-2",
        ts: new Date(now - 199 * 60000).toISOString(),
        raw: { content: "Successfully wrote data/specs/TASK-2026-0219-001_spec.md (156 lines)" },
      },
      {
        event_id: "tool-slack-2",
        kind: "tool_call",
        seq: 8,
        status: "completed",
        title: "mcp__slack__slack_send_message",
        tool_use_id: "tool-slack-2",
        preview: "Posting tech spec review request to #research-common",
        ts: new Date(now - 198 * 60000).toISOString(),
        raw: { input: { channel_id: "C06GHI789", thread_ts: "1706520000.000000", text: "Tech Spec Review Request: RAG Pipeline for Internal Knowledge Base. Architecture: pgvector + hybrid search + cross-encoder re-ranking. Please review and approve." } },
      },
      {
        event_id: "tool-slack-2-result",
        kind: "tool_result",
        seq: 9,
        status: "completed",
        title: "mcp__slack__slack_send_message",
        tool_use_id: "tool-slack-2",
        parent_event_id: "tool-slack-2",
        ts: new Date(now - 197 * 60000).toISOString(),
        raw: { content: "Message sent successfully to #research-common" },
      },
      {
        event_id: "sess-i9j0k1l2:output-1",
        kind: "assistant_output",
        seq: 10,
        status: "completed",
        preview: "Tech spec for RAG pipeline has been written and posted for review. Architecture: pgvector for vector storage, hybrid search combining BM25 + dense embeddings, cross-encoder re-ranking. Waiting for approval before proceeding to implementation.",
        ts: new Date(now - 196 * 60000).toISOString(),
      },
    ],
    // Default for sessions not listed
    "sess-m3n4o5p6": [],
    "sess-q7r8s9t0": [],
    "sess-u1v2w3x4": [],
  };

  return eventSets[sessionId] || [];
}

// ===== MOCK API LAYER =====

async function fetchJson(url) {
  // Simulate network delay
  await new Promise(r => setTimeout(r, 150 + Math.random() * 200));

  // Route mock responses
  if (url.includes("/api/threads?")) {
    const params = new URLSearchParams(url.split("?")[1]);
    const page = Number(params.get("page") || 1);
    const pageSize = Number(params.get("page_size") || THREAD_PAGE_SIZE);
    const start = (page - 1) * pageSize;
    const pageThreads = MOCK_THREADS.slice(start, start + pageSize);
    return {
      threads: pageThreads,
      total: MOCK_THREADS.length,
      page,
      page_size: pageSize,
      total_pages: Math.ceil(MOCK_THREADS.length / pageSize),
    };
  }

  if (url.includes("/sessions") && url.includes("/worktree")) {
    // Extract session ID from URL
    const sessionMatch = url.match(/sessions\/([^/]+)\/worktree/);
    const sessionId = sessionMatch ? decodeURIComponent(sessionMatch[1]) : "";
    const events = generateMockEvents(sessionId);
    return {
      events,
      cursor: events.length,
      range_start_seq: events.length > 0 ? 1 : 0,
      range_end_seq: events.length,
      has_older: false,
      total_events: events.length,
    };
  }

  if (url.includes("/sessions")) {
    // Find thread from URL
    const threadMatch = url.match(/threads\/[^/]+\/([^/]+)\/sessions/);
    const threadTs = threadMatch ? decodeURIComponent(threadMatch[1]) : "";
    const thread = MOCK_THREADS.find(t => t.thread_ts === threadTs);
    const threadId = thread ? thread.thread_id : "";
    const sessions = MOCK_SESSIONS[threadId] || [];
    return {
      sessions,
      latest_session_id: sessions.length > 0 ? sessions[sessions.length - 1].session_id : null,
    };
  }

  return {};
}

// ===== APPLICATION STATE =====

const state = {
  threadsById: new Map(),
  threadOrder: [],
  threadMeta: {
    total: 0,
    page: 1,
    pageSize: THREAD_PAGE_SIZE,
    totalPages: 0,
  },
  sessionsByThread: new Map(),
  eventsBySession: new Map(),
  eventIdsBySession: new Map(),
  sessionCursorById: new Map(),
  sessionRangeById: new Map(),
  streamUiBySession: new Map(),
  selectedThreadId: null,
  selectedSessionId: null,
  loadingThreadId: null,
  loadingThreadSessions: false,
  loadingSessionId: null,
  loadingOlderBySession: new Set(),
  threadPollTimer: null,
  sse: null,
  sseThreadId: null,
  drawerOpen: false,
  composerBusy: false,
  terminatingSessionId: null,
};

const el = {
  appShell: document.querySelector(".app-shell"),
  threadSidebar: document.getElementById("threadSidebar"),
  sidebarBackdrop: document.getElementById("sidebarBackdrop"),
  mobileThreadsOpen: document.getElementById("mobileThreadsOpen"),
  mobileThreadsClose: document.getElementById("mobileThreadsClose"),
  connectionBadge: document.getElementById("connectionBadge"),
  threadList: document.getElementById("threadList"),
  threadsTotal: document.getElementById("threadsTotal"),
  threadsPrev: document.getElementById("threadsPrev"),
  threadsNext: document.getElementById("threadsNext"),
  threadsPageLabel: document.getElementById("threadsPageLabel"),
  breadcrumbThread: document.getElementById("breadcrumbThread"),
  breadcrumbSession: document.getElementById("breadcrumbSession"),
  sessionStatusBadge: document.getElementById("sessionStatusBadge"),
  sessionUpdatedAt: document.getElementById("sessionUpdatedAt"),
  topologyMeta: document.getElementById("topologyMeta"),
  sessionTopology: document.getElementById("sessionTopology"),
  streamPane: document.getElementById("streamPane"),
  sessionStartChip: document.getElementById("sessionStartChip"),
  streamControls: document.getElementById("streamControls"),
  toggleToolsOnly: document.getElementById("toggleToolsOnly"),
  streamHiddenMeta: document.getElementById("streamHiddenMeta"),
  pinnedList: document.getElementById("pinnedList"),
  streamList: document.getElementById("streamList"),
  emptyState: document.getElementById("emptyState"),
  streamLoading: document.getElementById("streamLoading"),
  terminateSessionBtn: document.getElementById("terminateSessionBtn"),
  composerInput: document.getElementById("composerInput"),
  composerSend: document.getElementById("composerSend"),
};

boot().catch((error) => {
  console.error("Worktree dashboard boot failed", error);
  setConnectionBadge(false);
});

async function boot() {
  bindEvents();
  renderComposer();
  renderSessionActions();
  await refreshThreads({ preserveSelection: true, loadSelected: true, allowPageSearch: true });
  setConnectionBadge(true);
}

function bindEvents() {
  if (el.mobileThreadsOpen) {
    el.mobileThreadsOpen.addEventListener("click", () => {
      setMobileDrawerOpen(true);
    });
  }

  if (el.mobileThreadsClose) {
    el.mobileThreadsClose.addEventListener("click", () => {
      setMobileDrawerOpen(false);
    });
  }

  if (el.sidebarBackdrop) {
    el.sidebarBackdrop.addEventListener("click", () => {
      setMobileDrawerOpen(false);
    });
  }

  if (el.threadList) {
    el.threadList.addEventListener("click", (event) => {
      const sessionRow = event.target.closest("[data-session-id]");
      if (sessionRow) {
        const threadId = sessionRow.getAttribute("data-thread-id");
        const sessionId = sessionRow.getAttribute("data-session-id");
        if (!threadId || !sessionId) return;

        if (threadId !== state.selectedThreadId) {
          selectThread(threadId, { preferredSessionId: sessionId }).catch(console.error);
          setMobileDrawerOpen(false);
          return;
        }

        selectSession(sessionId).catch(console.error);
        setMobileDrawerOpen(false);
        return;
      }

      const threadCard = event.target.closest("[data-thread-id]");
      if (!threadCard) return;
      const threadId = threadCard.getAttribute("data-thread-id");
      if (!threadId) return;
      selectThread(threadId).catch(console.error);
      setMobileDrawerOpen(false);
    });
  }

  if (el.sessionTopology) {
    el.sessionTopology.addEventListener("click", (event) => {
      const node = event.target.closest("[data-session-id]");
      if (!node) return;
      const sessionId = node.getAttribute("data-session-id");
      if (!sessionId) return;
      selectSession(sessionId).catch(console.error);
    });
  }

  if (el.threadsPrev) {
    el.threadsPrev.addEventListener("click", () => {
      if (state.threadMeta.page <= 1) return;
      state.threadMeta.page -= 1;
      refreshThreads({ preserveSelection: true, loadSelected: true, allowPageSearch: false }).catch(console.error);
    });
  }

  if (el.threadsNext) {
    el.threadsNext.addEventListener("click", () => {
      if (state.threadMeta.totalPages && state.threadMeta.page >= state.threadMeta.totalPages) return;
      state.threadMeta.page += 1;
      refreshThreads({ preserveSelection: true, loadSelected: true, allowPageSearch: false }).catch(console.error);
    });
  }

  if (el.streamPane) {
    el.streamPane.addEventListener("click", (event) => {
      const sessionId = state.selectedSessionId;
      if (!sessionId) return;

      const toggleToolsOnly = event.target.closest("[data-action='toggle-tools-only']");
      if (toggleToolsOnly) {
        const ui = getSessionUiState(sessionId);
        ui.collapseToolsOnly = !ui.collapseToolsOnly;
        renderStreamFull({ progressive: false });
        return;
      }

      const toggleResult = event.target.closest("[data-action='toggle-tool-result']");
      if (toggleResult) {
        const eventId = toggleResult.getAttribute("data-event-id");
        if (!eventId) return;
        const ui = getSessionUiState(sessionId);
        if (ui.expandedResultIds.has(eventId)) {
          ui.expandedResultIds.delete(eventId);
        } else {
          ui.expandedResultIds.add(eventId);
        }
        renderStreamFull({ progressive: false });
      }
    });
  }

  if (el.composerInput) {
    el.composerInput.addEventListener("input", () => {
      renderComposer();
    });

    el.composerInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey) return;
      event.preventDefault();
    });
  }

  if (el.terminateSessionBtn) {
    el.terminateSessionBtn.addEventListener("click", () => {
      // No-op in demo mode
    });
  }

  window.addEventListener("resize", () => {
    if (!isDrawerMode()) {
      setMobileDrawerOpen(false);
    }
  });
}

async function refreshThreads({ preserveSelection, loadSelected, allowPageSearch }) {
  const targetPage = Math.max(1, Number(state.threadMeta.page || 1));
  const payload = await fetchJson(
    `/api/threads?page=${targetPage}&page_size=${THREAD_PAGE_SIZE}`,
  );
  const threads = Array.isArray(payload?.threads) ? payload.threads : [];

  const nextMap = new Map();
  const nextOrder = [];
  threads.forEach((thread) => {
    const id = String(thread.thread_id || "");
    if (!id) return;
    nextMap.set(id, thread);
    nextOrder.push(id);
  });

  const previousSelected = state.selectedThreadId;

  state.threadsById = nextMap;
  state.threadOrder = nextOrder;
  state.threadMeta.total = Number(payload?.total || 0);
  state.threadMeta.page = Math.max(1, Number(payload?.page || targetPage || 1));
  state.threadMeta.pageSize = Math.max(1, Number(payload?.page_size || THREAD_PAGE_SIZE));
  state.threadMeta.totalPages = Math.max(0, Number(payload?.total_pages || 0));

  if (!preserveSelection || !previousSelected || !nextMap.has(previousSelected)) {
    state.selectedThreadId = nextOrder[0] || null;
  }

  renderThreadList();
  renderThreadPagination();

  if (!state.selectedThreadId) {
    setThreadLoading(null, false);
    renderHeader();
    renderTopology();
    renderStreamFull({ progressive: false });
    return;
  }

  if (loadSelected) {
    await loadThreadSessions(state.selectedThreadId, { forceReload: true });
  } else {
    renderHeader();
  }
}

async function selectThread(threadId, options = {}) {
  if (!state.threadsById.has(threadId)) return;

  const previousThreadId = state.selectedThreadId;
  state.selectedThreadId = threadId;

  if (previousThreadId !== threadId) {
    state.selectedSessionId = null;
    setThreadLoading(threadId, true);
    renderThreadList();
    renderTopology();
    renderHeader();
    renderStreamLoadingSkeleton();
  }

  await loadThreadSessions(threadId, {
    forceReload: true,
    preferredSessionId: options.preferredSessionId || null,
  });
}

async function loadThreadSessions(
  threadId,
  { forceReload = false, preferredSessionId = null } = {},
) {
  const thread = state.threadsById.get(threadId);
  if (!thread) return;

  if (!forceReload && state.sessionsByThread.has(threadId)) {
    const cached = state.sessionsByThread.get(threadId) || [];
    const nextSessionId =
      preferredSessionId ||
      state.selectedSessionId ||
      thread.latest_session_id ||
      cached[cached.length - 1]?.session_id ||
      null;

    renderThreadList();
    renderTopology();
    renderHeader();

    if (nextSessionId) {
      await selectSession(nextSessionId, { preferCache: true });
    } else {
      renderStreamFull({ progressive: false });
    }
    if (isThreadLoading(threadId)) {
      setThreadLoading(threadId, false);
      renderThreadList();
      renderTopology();
      renderHeader();
    }
    return;
  }

  const shouldShowThreadLoading = state.selectedThreadId === threadId;
  if (shouldShowThreadLoading) {
    setThreadLoading(threadId, true);
    renderThreadList();
    renderTopology();
    renderHeader();
  }

  try {
    const url = `/api/threads/${encodeURIComponent(thread.channel_id)}/${encodeURIComponent(
      thread.thread_ts,
    )}/sessions`;
    const payload = await fetchJson(url);
    const sessions = Array.isArray(payload?.sessions) ? payload.sessions : [];
    sessions.sort((a, b) => toTimeValue(a.created_at) - toTimeValue(b.created_at));

    state.sessionsByThread.set(threadId, sessions);

    const nextSessionId =
      preferredSessionId ||
      state.selectedSessionId ||
      payload?.latest_session_id ||
      thread.latest_session_id ||
      sessions[sessions.length - 1]?.session_id ||
      null;

    renderThreadList();
    renderTopology();
    renderHeader();

    if (nextSessionId) {
      await selectSession(nextSessionId, { preferCache: true });
    } else {
      renderStreamFull({ progressive: false });
    }
  } finally {
    if (shouldShowThreadLoading && state.selectedThreadId === threadId) {
      setThreadLoading(threadId, false);
      renderThreadList();
      renderTopology();
      renderHeader();
    }
  }
}

async function selectSession(sessionId, { preferCache = false } = {}) {
  const threadId = state.selectedThreadId;
  if (!threadId) return;

  const sessions = state.sessionsByThread.get(threadId) || [];
  const exists = sessions.some((session) => session.session_id === sessionId);
  if (!exists) return;

  state.selectedSessionId = sessionId;

  renderThreadList();
  renderTopology();
  requestAnimationFrame(() => ensureTopologySelectionVisible(sessionId));
  renderHeader();

  await loadSessionWorktree(sessionId, {
    replace: true,
    preferCache,
    limit: INITIAL_EVENT_LIMIT,
    showLoading: true,
    beforeSeq: 0,
  });
}

async function loadSessionWorktree(
  sessionId,
  { replace, preferCache, limit, showLoading, beforeSeq },
) {
  const thread = getSelectedThread();
  if (!thread) return;

  if (replace && preferCache && state.eventsBySession.has(sessionId)) {
    renderStreamFull({ progressive: false });
    return;
  }

  if (showLoading) {
    setSessionLoading(sessionId, true);
    renderStreamLoadingSkeleton();
  }

  const params = new URLSearchParams();
  if (limit > 0) params.set("limit", String(limit));
  if (beforeSeq > 0) params.set("before_seq", String(beforeSeq));

  const url = `/api/threads/${encodeURIComponent(thread.channel_id)}/${encodeURIComponent(
    thread.thread_ts,
  )}/sessions/${encodeURIComponent(sessionId)}/worktree${
    params.toString() ? `?${params.toString()}` : ""
  }`;

  const payload = await fetchJson(url);
  const events = Array.isArray(payload?.events) ? payload.events : [];
  const cursor = Number(payload?.cursor || 0);

  if (replace) {
    state.eventsBySession.set(sessionId, events);
    state.eventIdsBySession.set(
      sessionId,
      new Set(events.map((event) => String(event.event_id || "")).filter(Boolean)),
    );
  } else {
    prependOrAppendEvents(sessionId, events, beforeSeq > 0);
  }

  state.sessionCursorById.set(sessionId, cursor);

  const range = state.sessionRangeById.get(sessionId) || {
    minSeq: Number.MAX_SAFE_INTEGER,
    maxSeq: 0,
    hasOlder: false,
    totalEvents: 0,
  };

  const rangeStart = Number(payload?.range_start_seq || 0);
  const rangeEnd = Number(payload?.range_end_seq || 0);

  if (rangeStart > 0) {
    range.minSeq = Math.min(range.minSeq, rangeStart);
  } else if (replace) {
    range.minSeq = 0;
  }

  if (rangeEnd > 0) {
    range.maxSeq = Math.max(range.maxSeq, rangeEnd);
  }

  if (typeof payload?.has_older === "boolean") {
    range.hasOlder = payload.has_older;
  }
  range.totalEvents = Number(payload?.total_events || range.totalEvents || events.length);
  state.sessionRangeById.set(sessionId, range);

  touchSessionCountsByFullEvents(sessionId);

  if (showLoading) {
    setSessionLoading(sessionId, false);
  }

  renderStreamFull({ progressive: replace });
}

function prependOrAppendEvents(sessionId, incomingEvents, prepend) {
  const list = state.eventsBySession.get(sessionId) || [];
  const seen = state.eventIdsBySession.get(sessionId) || new Set();
  const bucket = [];

  incomingEvents.forEach((event) => {
    const eventId = String(event.event_id || "");
    if (!eventId || seen.has(eventId)) return;
    seen.add(eventId);
    bucket.push(event);
  });

  if (!bucket.length) {
    state.eventIdsBySession.set(sessionId, seen);
    return;
  }

  const next = prepend ? [...bucket, ...list] : [...list, ...bucket];
  next.sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));

  state.eventsBySession.set(sessionId, next);
  state.eventIdsBySession.set(sessionId, seen);
}

function renderThreadList() {
  if (!el.threadList) return;

  const html = state.threadOrder
    .map((threadId) => {
      const thread = state.threadsById.get(threadId);
      if (!thread) return "";

      const active = threadId === state.selectedThreadId;
      const sessions = state.sessionsByThread.get(threadId) || [];

      let sessionListHtml = "";
      if (active) {
        if (isThreadLoading(threadId)) {
          sessionListHtml = renderThreadSessionLoading();
        } else {
          sessionListHtml = `<div class="thread-sessions">${sessions
            .map((session) => renderThreadSessionItem(threadId, session))
            .join("")}</div>`;
        }
      }

      return `
        <article class="thread-card ${active ? "active" : ""}" data-thread-id="${escapeHtml(threadId)}">
          <div class="thread-head">
            <div class="thread-title">${escapeHtml(thread.title || `${thread.channel_id}/${thread.thread_ts}`)}</div>
            <div class="thread-updated">${escapeHtml(formatRelativeTime(thread.updated_at))}</div>
          </div>
          <div class="thread-meta">
            <span>#${escapeHtml(thread.channel_name || thread.channel_id || "-")}</span>
            <span>req ${Number(thread.request_count || 0)}</span>
            <span>sess ${Number(thread.session_count || 0)}</span>
            <span>live ${Number(thread.live_session_count || 0)}</span>
          </div>
          <div class="thread-snippet">${escapeHtml(truncate(thread.latest_text || "(no message)", 88))}</div>
          ${sessionListHtml}
        </article>
      `;
    })
    .join("");

  el.threadList.innerHTML = html || '<div class="empty-state">No threads available.</div>';

  if (el.threadsTotal) {
    el.threadsTotal.textContent = String(state.threadMeta.total || 0);
  }
}

function renderThreadSessionItem(threadId, session) {
  const active = session.session_id === state.selectedSessionId;
  const status = normalizeStatus(session.status);
  const counts = session.event_counts || {};

  return `
    <div class="thread-session-item ${active ? "active" : ""}" data-thread-id="${escapeHtml(
      threadId,
    )}" data-session-id="${escapeHtml(session.session_id || "")}">
      <div class="thread-session-top">
        <span class="session-mini-id">${escapeHtml(shortSession(session.session_id))}</span>
        <span class="session-mini-status ${statusClass(status)}">${escapeHtml(status)}</span>
      </div>
      <div class="thread-meta">
        <span>tools ${Number(counts.tool_call || 0)}</span>
        <span>events ${Number(session.event_count || 0)}</span>
        <span>${escapeHtml(formatRelativeTime(session.updated_at))}</span>
      </div>
    </div>
  `;
}

function renderThreadSessionLoading() {
  return `
    <div class="thread-sessions loading">
      <div class="thread-session-loading">
        <span class="thread-loading-spinner" aria-hidden="true"></span>
        <span>Loading sessions...</span>
      </div>
      <div class="thread-session-skeleton"></div>
      <div class="thread-session-skeleton"></div>
    </div>
  `;
}

function renderThreadPagination() {
  if (el.threadsPageLabel) {
    const current = Number(state.threadMeta.page || 1);
    const totalPages = Number(state.threadMeta.totalPages || 0);
    el.threadsPageLabel.textContent = totalPages
      ? `Page ${current}/${totalPages}`
      : "Page 1/0";
  }

  if (el.threadsPrev) {
    el.threadsPrev.disabled = state.threadMeta.page <= 1;
  }
  if (el.threadsNext) {
    const totalPages = Number(state.threadMeta.totalPages || 0);
    el.threadsNext.disabled = totalPages <= 0 || state.threadMeta.page >= totalPages;
  }
}

function renderHeader() {
  const thread = getSelectedThread();
  const session = getSelectedSession();

  if (!thread) {
    el.breadcrumbThread.textContent = "-";
    el.breadcrumbSession.textContent = "-";
    setStatusBadge(el.sessionStatusBadge, "pending");
    el.sessionUpdatedAt.textContent = "-";
    renderSessionActions();
    return;
  }

  el.breadcrumbThread.textContent = `${thread.title || `${thread.channel_id}/${thread.thread_ts}`}`;

  if (!session) {
    el.breadcrumbSession.textContent = "No session selected";
    setStatusBadge(el.sessionStatusBadge, normalizeStatus(thread.status));
    el.sessionUpdatedAt.textContent = formatDateTime(thread.updated_at);
    renderSessionActions();
    return;
  }

  el.breadcrumbSession.textContent = `${shortSession(session.session_id)} \u00b7 ${truncate(
    session.request_preview || session.summary || "",
    48,
  )}`;
  setStatusBadge(el.sessionStatusBadge, normalizeStatus(session.status));
  el.sessionUpdatedAt.textContent = formatDateTime(session.updated_at);
  renderSessionActions();
}

function isDrawerMode() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 920px)").matches
  );
}

function setMobileDrawerOpen(open) {
  const shouldOpen = Boolean(open) && isDrawerMode();
  state.drawerOpen = shouldOpen;
  document.body.classList.toggle("sidebar-open", shouldOpen);
}

function adjustComposerHeight() {
  if (!el.composerInput) return;
  el.composerInput.style.height = "auto";
  const next = Math.min(140, Math.max(44, el.composerInput.scrollHeight));
  el.composerInput.style.height = `${next}px`;
}

function renderComposer() {
  if (!el.composerInput || !el.composerSend) return;

  const hasThread = Boolean(state.selectedThreadId);

  el.composerInput.disabled = true;
  el.composerInput.placeholder = "Demo mode - input disabled";

  el.composerSend.disabled = true;
  adjustComposerHeight();
}

function renderSessionActions() {
  renderComposer();

  if (!el.terminateSessionBtn) return;
  el.terminateSessionBtn.disabled = true;
  el.terminateSessionBtn.textContent = "Terminate";
}

function renderTopology() {
  if (!el.sessionTopology || !el.topologyMeta) return;

  const threadId = state.selectedThreadId;
  if (!threadId) {
    el.sessionTopology.innerHTML = "";
    el.topologyMeta.textContent = "0 sessions";
    return;
  }

  const sessions = state.sessionsByThread.get(threadId) || [];

  if (isThreadLoading(threadId)) {
    el.topologyMeta.textContent = "loading...";
    el.sessionTopology.innerHTML = new Array(3)
      .fill(0)
      .map(
        () => `
          <article class="topology-node topology-loading-node" aria-hidden="true">
            <div class="topology-node-dot topology-loading-dot"></div>
            <div class="topology-skeleton-line s1"></div>
            <div class="topology-skeleton-line s2"></div>
            <div class="topology-skeleton-line s3"></div>
          </article>
        `,
      )
      .join("");
    return;
  }

  el.topologyMeta.textContent = `${sessions.length} sessions`;

  const html = sessions
    .map((session, index) => {
      const active = session.session_id === state.selectedSessionId;
      const status = normalizeStatus(session.status);
      const counts = session.event_counts || {};
      const icon = iconForStatus(status);
      const tooltipText = session.request_preview || session.summary || "Session";

      return `
        <article class="topology-node ${active ? "active" : ""} ${statusClass(status)}" data-session-id="${escapeHtml(
          session.session_id,
        )}" data-tooltip="${escapeHtml(tooltipText)}" title="${escapeHtml(tooltipText)}" tabindex="0">
          <div class="topology-node-dot">
            <iconify-icon icon="${escapeHtml(icon)}" width="10"></iconify-icon>
          </div>
          <div class="topology-node-id">${escapeHtml(shortSession(session.session_id))}</div>
          <div class="topology-node-title">${escapeHtml(truncate(tooltipText, 46))}</div>
          <div class="topology-node-meta">
            <span>${escapeHtml(status)}</span>
            <span>tool ${Number(counts.tool_call || 0)}</span>
            <span>${escapeHtml(formatRelativeTime(session.updated_at))}</span>
          </div>
          ${index < sessions.length - 1 ? '<div class="topology-link"></div>' : ""}
        </article>
      `;
    })
    .join("");

  el.sessionTopology.innerHTML = html;

  if (state.selectedSessionId) {
    requestAnimationFrame(() => ensureTopologySelectionVisible(state.selectedSessionId));
  }
}

function ensureTopologySelectionVisible(sessionId) {
  if (!el.sessionTopology || !sessionId) return;

  const target = el.sessionTopology.querySelector(
    `.topology-node[data-session-id="${cssEscape(sessionId)}"]`,
  );
  if (!target) return;

  target.scrollIntoView({ block: "nearest", inline: "center", behavior: "auto" });
}

function renderStreamLoadingSkeleton() {
  if (!el.streamList || !el.streamLoading || !el.streamPane) return;

  el.streamPane.setAttribute("aria-busy", "true");
  el.streamLoading.style.display = "block";
  el.emptyState.style.display = "none";
  renderStreamControls([], null);
  if (el.pinnedList) el.pinnedList.innerHTML = "";

  const skeleton = new Array(5)
    .fill(0)
    .map(
      (_, idx) => `
        <article class="timeline-item skeleton-item ${idx === 4 ? "last" : ""}">
          <div class="timeline-icon skeleton-dot"></div>
          <div class="timeline-card skeleton-card">
            <div class="skeleton-line w40"></div>
            <div class="skeleton-line w85"></div>
            <div class="skeleton-line w68"></div>
          </div>
        </article>
      `,
    )
    .join("");

  el.streamList.innerHTML = skeleton;
}

function getPinnedEvents(events) {
  const list = Array.isArray(events) ? events : [];
  const pinned = [];

  const commandCandidates = list.filter(
    (event) =>
      String(event.kind || "") === "user_command" &&
      (String(event.event_id || "").endsWith(":command") ||
        String(event.raw?.type || "") === "user_input"),
  );

  const commandPreferred =
    commandCandidates.find((event) => String(event.event_id || "").endsWith(":command")) ||
    commandCandidates[0] ||
    null;

  if (commandPreferred) pinned.push(commandPreferred);

  const startedCandidates = list.filter(
    (event) =>
      String(event.kind || "") === "assistant_observation" &&
      String(event.raw?.type || "") === "processing_started",
  );

  if (startedCandidates.length) {
    startedCandidates.sort((a, b) => toTimeValue(a.ts) - toTimeValue(b.ts));
    pinned.push(startedCandidates[startedCandidates.length - 1]);
  }

  const pinnedIds = new Set(
    [...commandCandidates, ...startedCandidates]
      .map((event) => String(event.event_id || ""))
      .filter(Boolean),
  );

  return { pinned, pinnedIds };
}

function renderPinnedEvents(sessionId, events) {
  if (!el.pinnedList) return;

  if (!sessionId) {
    el.pinnedList.innerHTML = "";
    return;
  }

  const { pinned } = getPinnedEvents(events);

  if (!pinned.length) {
    el.pinnedList.innerHTML = "";
    return;
  }

  const html = pinned
    .map((event, index) =>
      renderEventCard(event, {
        animate: false,
        last: index === pinned.length - 1,
      }),
    )
    .join("");

  el.pinnedList.innerHTML = html;
}

function renderStreamFull({ progressive }) {
  const sessionId = state.selectedSessionId;
  const session = getSelectedSession();

  if (!sessionId || !session) {
    el.sessionStartChip.textContent = "Session -";
    el.streamList.innerHTML = "";
    renderStreamControls([], null);
    if (el.pinnedList) el.pinnedList.innerHTML = "";
    el.emptyState.style.display = "block";
    if (el.streamLoading) el.streamLoading.style.display = "none";
    if (el.streamPane) el.streamPane.setAttribute("aria-busy", "false");
    return;
  }

  const events = state.eventsBySession.get(sessionId) || [];
  const { pinnedIds } = getPinnedEvents(events);
  const mainEvents = events.filter((event) => !pinnedIds.has(String(event.event_id || "")));
  renderPinnedEvents(sessionId, events);
  const blocks = buildStreamBlocks(sessionId, mainEvents);

  el.sessionStartChip.textContent = `${shortSession(sessionId)} started ${formatDateTime(
    session.created_at,
  )}`;
  renderStreamControls(mainEvents, sessionId);

  if (!blocks.length) {
    el.streamList.innerHTML = "";
    el.emptyState.style.display = "block";
    if (el.streamLoading) el.streamLoading.style.display = "none";
    if (el.streamPane) el.streamPane.setAttribute("aria-busy", "false");
    return;
  }

  el.emptyState.style.display = "none";

  renderBlockListSync(sessionId, blocks);

  if (el.streamLoading) el.streamLoading.style.display = "none";
  if (el.streamPane) el.streamPane.setAttribute("aria-busy", "false");
}

function renderBlockListSync(sessionId, blocks) {
  const ui = getSessionUiState(sessionId);
  const html = blocks
    .map((block, index) =>
      renderStreamBlock(block, {
        animate: false,
        last: index === blocks.length - 1,
        sessionUi: ui,
      }),
    )
    .join("");
  el.streamList.innerHTML = html;
}

function renderStreamControls(events, sessionId) {
  if (!el.streamControls || !el.toggleToolsOnly || !el.streamHiddenMeta) {
    return;
  }

  if (!sessionId) {
    el.streamControls.style.display = "none";
    return;
  }

  el.streamControls.style.display = "flex";
  const ui = getSessionUiState(sessionId);
  const thinkingCount = events.filter((event) => event.kind === "assistant_thinking").length;
  const toolCount = events.filter((event) => isToolEvent(event.kind)).length;
  let hiddenTools = 0;

  if (ui.collapseToolsOnly) {
    hiddenTools = toolCount;
  }

  el.toggleToolsOnly.classList.toggle("active", ui.collapseToolsOnly);
  el.toggleToolsOnly.textContent = ui.collapseToolsOnly ? `Expand Tools (${hiddenTools})` : "Collapse Tools Only";
  el.streamHiddenMeta.textContent = hiddenTools
    ? `hidden: tools ${hiddenTools}`
    : `thinking ${thinkingCount}, tools ${toolCount}`;
}

function buildStreamBlocks(sessionId, events) {
  const ui = getSessionUiState(sessionId);
  const groups = buildToolGroups(events);
  const groupedToolBySeq = new Map();
  const groupedToolIds = new Set();

  groups.forEach((group) => {
    const seq = Number(group.call?.seq || group.result?.seq || 0);
    if (!seq) return;
    groupedToolBySeq.set(seq, group);
    if (group.call?.event_id) groupedToolIds.add(String(group.call.event_id));
    if (group.result?.event_id) groupedToolIds.add(String(group.result.event_id));
  });

  const blocks = [];
  const sorted = [...events].sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));
  sorted.forEach((event) => {
    const kind = String(event.kind || "");
    const seq = Number(event.seq || 0);

    if (isToolEvent(kind)) {
      if (ui.collapseToolsOnly) return;

      if (kind === "tool_result") {
        const parentGroupId = String(event.tool_use_id || event.parent_event_id || "");
        const hasCall = groups.some((group) => group.groupId === parentGroupId && group.call);
        if (hasCall) return;
      }

      const group = groupedToolBySeq.get(seq);
      if (group) {
        blocks.push({ type: "tool", event, group });
        return;
      }

      blocks.push({
        type: "tool",
        event,
        group: {
          groupId: String(event.tool_use_id || event.parent_event_id || event.event_id || ""),
          call: kind === "tool_call" ? event : null,
          result: kind === "tool_result" ? event : null,
        },
      });
      return;
    }

    if (groupedToolIds.has(String(event.event_id || ""))) return;

    blocks.push({ type: "event", event });
  });

  return blocks;
}

function renderStreamBlock(block, { animate, last, sessionUi }) {
  if (block.type === "tool") {
    return renderToolTimelineItem(block.group, { animate, last, sessionUi });
  }
  return renderEventCard(block.event, { animate, last });
}

function renderEventCard(event, { animate, last }) {
  const kind = String(event.kind || "assistant_observation");
  const title = humanKind(kind);
  const summary = event.preview || event.summary || event.title || "";
  const status = normalizeStatus(event.status);
  const seq = Number(event.seq || 0);

  return `
    <article class="timeline-item notranslate ${animate ? "event-enter" : ""} ${last ? "last" : ""}" data-event-id="${escapeHtml(
      event.event_id || "",
    )}" data-seq="${seq}" translate="no">
      <div class="timeline-icon ${statusClass(status)} kind-${escapeHtml(kind)}">
        <iconify-icon icon="${escapeHtml(iconForKind(kind))}" width="13"></iconify-icon>
      </div>
      <div class="timeline-card kind-${escapeHtml(kind)}">
        <div class="timeline-head">
          <div class="timeline-title-wrap">
            <span class="timeline-title">${escapeHtml(title)}</span>
            <span class="timeline-badge ${statusClass(status)}">${escapeHtml(status)}</span>
          </div>
          <span class="timeline-ts">${escapeHtml(formatTime(event.ts))}</span>
        </div>
        <div class="timeline-summary">${escapeHtml(summary)}</div>
        <div class="timeline-meta">${escapeHtml(truncate(event.event_id || "", 48))}</div>
      </div>
    </article>
  `;
}

function renderToolTimelineItem(group, { animate, last, sessionUi }) {
  const call = group.call;
  const result = group.result;
  const title = String(call?.title || result?.title || "Tool");
  const ts = String(result?.ts || call?.ts || "");
  const status = resolveToolStatus(call, result);
  const seq = Number(group.firstSeq || call?.seq || result?.seq || 0);

  return `
    <article class="timeline-item notranslate ${animate ? "event-enter" : ""} ${last ? "last" : ""}" data-tool-group-id="${escapeHtml(
      group.groupId || "",
    )}" data-seq="${seq}" translate="no">
      <div class="timeline-icon ${statusClass(status)} kind-tool">
        <iconify-icon icon="solar:terminal-2-bold" width="13"></iconify-icon>
      </div>
      <div class="timeline-card kind-tool">
        <div class="timeline-head">
          <div class="timeline-title-wrap">
            <span class="timeline-title">${escapeHtml(title)}</span>
            <span class="timeline-badge ${statusClass(status)}">${escapeHtml(status)}</span>
          </div>
          <span class="timeline-ts">${escapeHtml(formatTime(ts))}</span>
        </div>
        ${renderToolCard(group, sessionUi)}
      </div>
    </article>
  `;
}

function renderToolCard(group, uiState) {
  const call = group.call;
  const result = group.result;
  const name = String(call?.title || result?.title || "Tool");
  const family = toolFamily(name);

  const status = resolveToolStatus(call, result);
  const resultEventId = result?.event_id || "";
  const expanded = resultEventId ? uiState.expandedResultIds.has(resultEventId) : false;

  const renderedInput = renderToolInput(name, family, call?.raw?.input, call?.preview || call?.summary);
  const renderedOutput = renderToolOutput(name, family, result, expanded, TOOL_PREVIEW_LIMIT);

  const showToggle = renderedOutput.canToggle;
  const toggleButton = showToggle
    ? `<button class="inline-action" type="button" data-action="toggle-tool-result" data-event-id="${escapeHtml(
        resultEventId,
      )}">${expanded ? "Collapse" : "Expand"}</button>`
    : "";

  return `
    <div class="tool-card ${escapeHtml(status)}">
      <div class="tool-head">
        <div class="tool-title-wrap">
          <iconify-icon icon="${escapeHtml(iconForToolFamily(family))}" width="12"></iconify-icon>
          <span class="tool-name">${escapeHtml(name)}</span>
        </div>
        <span class="tool-status ${escapeHtml(status)}">${escapeHtml(status)}</span>
      </div>
      <div class="tool-content ${escapeHtml(family)}">
        ${renderedInput}
        ${renderedOutput.html}
        ${toggleButton}
      </div>
    </div>
  `;
}

function renderToolInput(name, family, input, fallback) {
  const pretty = formatToolValue(input, fallback || "-");

  if (family === "bash") {
    return `
      <div class="tool-terminal">
        <div class="tool-terminal-head"><span>bash</span></div>
        <pre class="tool-terminal-body">$ ${escapeHtml(pretty)}</pre>
      </div>
    `;
  }

  if (family === "file") {
    const parsed = normalizeObject(input);
    const path = parsed.path || parsed.file_path || parsed.file || parsed.filename || "(path unknown)";
    return `
      <div class="tool-block">
        <div class="tool-block-head">File Input</div>
        <div class="tool-kv"><span>path</span><span>${escapeHtml(String(path))}</span></div>
        <pre class="tool-block-body light">${escapeHtml(pretty)}</pre>
      </div>
    `;
  }

  if (family === "slack") {
    const parsed = normalizeObject(input);
    const rows = [
      ["channel", parsed.channel_id || "-"],
      ["thread", parsed.thread_ts || "-"],
      ["limit", parsed.limit || "-"],
    ];
    return `
      <div class="tool-block">
        <div class="tool-block-head">Slack Request</div>
        ${rows
          .map(([k, v]) => `<div class="tool-kv"><span>${escapeHtml(String(k))}</span><span>${escapeHtml(String(v))}</span></div>`)
          .join("")}
      </div>
    `;
  }

  if (family === "web") {
    return `
      <div class="tool-block">
        <div class="tool-block-head">Request</div>
        <pre class="tool-block-body light">${escapeHtml(pretty)}</pre>
      </div>
    `;
  }

  return `
    <div class="tool-block">
      <div class="tool-block-head">Input</div>
      <pre class="tool-block-body">${escapeHtml(pretty)}</pre>
    </div>
  `;
}

function renderToolOutput(name, family, resultEvent, expanded, previewLimit) {
  const fullText = extractToolResultText(resultEvent);
  const hasLong = fullText.length > previewLimit;
  const renderedText = expanded ? fullText : truncate(fullText, previewLimit);

  if (family === "todo") {
    const list = parseTodoItems(fullText);
    if (list.length) {
      return {
        html: `
          <div class="tool-block">
            <div class="tool-block-head">Todo</div>
            <ul class="tool-list">${list
              .map(
                (item) =>
                  `<li>${escapeHtml(item.done ? "[x]" : "[ ]")} ${escapeHtml(item.text)}</li>`,
              )
              .join("")}</ul>
          </div>
        `,
        canToggle: false,
      };
    }
  }

  if (family === "list" || family === "slack") {
    const rows = parseListRows(fullText);
    if (rows.length) {
      return {
        html: `
          <div class="tool-block">
            <div class="tool-block-head">Output</div>
            <ul class="tool-list">${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>
          </div>
        `,
        canToggle: hasLong,
      };
    }
  }

  if (family === "web") {
    return {
      html: `
        <div class="tool-block">
          <div class="tool-block-head">Response</div>
          <pre class="tool-block-body light">${escapeHtml(renderedText || "(pending result)")}</pre>
        </div>
      `,
      canToggle: hasLong,
    };
  }

  if (family === "bash") {
    return {
      html: `
        <div class="tool-terminal">
          <div class="tool-terminal-head"><span>output</span></div>
          <pre class="tool-terminal-body output">${escapeHtml(renderedText || "(pending result)")}</pre>
        </div>
      `,
      canToggle: hasLong,
    };
  }

  return {
    html: `
      <div class="tool-block">
        <div class="tool-block-head">Output</div>
        <pre class="tool-block-body light">${escapeHtml(renderedText || "(pending result)")}</pre>
      </div>
    `,
    canToggle: hasLong,
  };
}

function buildToolGroups(events) {
  const groups = [];
  const map = new Map();

  const sorted = [...events].sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));
  sorted.forEach((event) => {
    const kind = String(event.kind || "");
    if (!isToolEvent(kind)) return;

    let groupId = "";
    if (kind === "tool_call") {
      groupId = String(event.tool_use_id || event.event_id || "");
    } else {
      groupId = String(event.tool_use_id || event.parent_event_id || event.event_id || "");
    }
    if (!groupId) return;

    let group = map.get(groupId);
    if (!group) {
      group = {
        groupId,
        firstSeq: Number(event.seq || 0),
        call: null,
        result: null,
      };
      map.set(groupId, group);
      groups.push(group);
    }

    const seq = Number(event.seq || 0);
    if (!group.firstSeq || seq < group.firstSeq) {
      group.firstSeq = seq;
    }

    if (kind === "tool_call") {
      group.call = event;
    } else if (!group.result || Number(group.result.seq || 0) <= seq) {
      group.result = event;
    }
  });

  groups.sort((a, b) => a.firstSeq - b.firstSeq);
  return groups;
}

function touchSessionCountsByFullEvents(sessionId) {
  const threadId = state.selectedThreadId;
  if (!threadId) return;

  const events = state.eventsBySession.get(sessionId) || [];
  const session = getSessionById(threadId, sessionId);
  if (!session) return;

  const counts = {
    thinking: 0,
    tool_call: 0,
    tool_result: 0,
    output: 0,
  };

  events.forEach((event) => {
    if (event.kind === "assistant_thinking") counts.thinking += 1;
    if (event.kind === "tool_call") counts.tool_call += 1;
    if (event.kind === "tool_result") counts.tool_result += 1;
    if (event.kind === "assistant_output") counts.output += 1;
  });

  session.event_count = events.length;
  session.event_counts = counts;

  renderThreadList();
  renderTopology();
}

function getSelectedThread() {
  if (!state.selectedThreadId) return null;
  return state.threadsById.get(state.selectedThreadId) || null;
}

function getSelectedSession() {
  if (!state.selectedThreadId || !state.selectedSessionId) return null;
  return getSessionById(state.selectedThreadId, state.selectedSessionId);
}

function getSessionById(threadId, sessionId) {
  const sessions = state.sessionsByThread.get(threadId) || [];
  return sessions.find((session) => session.session_id === sessionId) || null;
}

function getSessionUiState(sessionId) {
  let item = state.streamUiBySession.get(sessionId);
  if (!item) {
    item = {
      collapseToolsOnly: false,
      expandedResultIds: new Set(),
    };
    state.streamUiBySession.set(sessionId, item);
  }
  return item;
}

function setSessionLoading(sessionId, loading) {
  if (loading) {
    state.loadingSessionId = sessionId;
  } else if (state.loadingSessionId === sessionId) {
    state.loadingSessionId = null;
  }
}

function setThreadLoading(threadId, loading) {
  if (loading && threadId) {
    state.loadingThreadId = threadId;
    state.loadingThreadSessions = true;
    return;
  }
  if (!threadId || state.loadingThreadId === threadId) {
    state.loadingThreadId = null;
    state.loadingThreadSessions = false;
  }
}

function isThreadLoading(threadId) {
  return Boolean(
    threadId &&
      state.loadingThreadSessions &&
      state.loadingThreadId &&
      state.loadingThreadId === threadId,
  );
}

function setConnectionBadge(live) {
  if (!el.connectionBadge) return;
  el.connectionBadge.textContent = live ? "LIVE" : "OFFLINE";
  el.connectionBadge.classList.toggle("offline", !live);
}

function setStatusBadge(node, status) {
  if (!node) return;
  node.textContent = status;
  node.className = `status-badge ${statusClass(status)}`;
}

function isToolEvent(kind) {
  return kind === "tool_call" || kind === "tool_result";
}

function normalizeStatus(status) {
  const value = String(status || "").toLowerCase();
  if (!value) return "pending";
  if (value.includes("cancel")) return "cancelled";
  if (value.includes("fail") || value.includes("error")) return "failed";
  if (value.includes("wait") || value.includes("pause")) return "waiting";
  if (value.includes("active") || value.includes("running") || value.includes("init")) return "active";
  if (value.includes("complete") || value.includes("done") || value.includes("success")) return "completed";
  return "pending";
}

function resolveToolStatus(callEvent, resultEvent) {
  const resultStatus = normalizeStatus(resultEvent?.status);
  if (resultStatus === "failed") return "error";
  if (resultEvent) return "ok";
  const callStatus = normalizeStatus(callEvent?.status);
  if (callStatus === "failed") return "error";
  return "running";
}

function statusClass(status) {
  const raw = String(status || "").toLowerCase();
  if (raw === "ok") return "status-completed";
  if (raw === "running") return "status-active";
  if (raw === "error") return "status-failed";
  if (raw === "cancelled") return "status-cancelled";
  const value = normalizeStatus(raw);
  return `status-${value}`;
}

function humanKind(kind) {
  switch (kind) {
    case "user_command": return "User Command";
    case "assistant_thinking": return "Thinking";
    case "assistant_observation": return "Observation";
    case "assistant_output": return "Assistant Output";
    default: return kind || "Event";
  }
}

function iconForKind(kind) {
  switch (kind) {
    case "user_command": return "solar:user-bold";
    case "assistant_thinking": return "solar:lightbulb-minimalistic-bold";
    case "assistant_observation": return "solar:telescope-bold";
    case "assistant_output": return "solar:chat-square-bold";
    default: return "solar:stars-bold";
  }
}

function iconForStatus(status) {
  const value = normalizeStatus(status);
  if (value === "completed") return "solar:check-circle-bold";
  if (value === "failed") return "solar:close-circle-bold";
  if (value === "cancelled") return "solar:stop-circle-bold";
  if (value === "active") return "solar:play-circle-bold";
  if (value === "waiting") return "solar:pause-circle-bold";
  return "solar:clock-circle-bold";
}

function toolFamily(toolName) {
  const name = String(toolName || "").toLowerCase();
  if (name === "bash" || name.includes("bash")) return "bash";
  if (["read", "edit", "write"].some((token) => name === token || name.endsWith(`_${token}`))) return "file";
  if (["grep", "glob", "toolsearch"].some((token) => name.includes(token))) return "list";
  if (["webfetch", "websearch"].some((token) => name.includes(token))) return "web";
  if (name.includes("todowrite")) return "todo";
  if (name.startsWith("mcp__slack") || name.startsWith("mcp__slack-bot")) return "slack";
  if (name.startsWith("mcp__playwright") || name.startsWith("mcp__browsermcp") || name.startsWith("mcp__puppeteer")) return "browser";
  return "generic";
}

function iconForToolFamily(family) {
  switch (family) {
    case "bash": return "solar:terminal-2-bold";
    case "file": return "solar:file-code-bold";
    case "slack": return "solar:hashtag-square-bold";
    case "web": return "solar:global-bold";
    case "todo": return "solar:checklist-minimalistic-bold";
    case "browser": return "solar:window-frame-bold";
    case "list": return "solar:list-check-bold";
    default: return "solar:code-square-bold";
  }
}

function extractToolResultText(resultEvent) {
  if (!resultEvent) return "";
  const raw = resultEvent.raw || {};
  const rawContent = raw.content;
  if (typeof rawContent === "string") return rawContent;
  if (Array.isArray(rawContent)) {
    const parts = rawContent
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object") {
          if (typeof part.text === "string") return part.text;
          try { return JSON.stringify(part, null, 2); } catch { return String(part); }
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join("\n");
  }
  if (rawContent && typeof rawContent === "object") {
    try { return JSON.stringify(rawContent, null, 2); } catch { return String(rawContent); }
  }
  return String(resultEvent.preview || resultEvent.summary || "");
}

function normalizeObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value;
}

function formatToolValue(value, fallback) {
  if (value === null || value === undefined || value === "") return fallback || "-";
  if (typeof value === "string") return value;
  try { return JSON.stringify(value, null, 2); } catch { return String(value); }
}

function parseTodoItems(text) {
  const rows = String(text || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  return rows
    .map((line) => {
      const match = line.match(/^[-*]?\s*\[(x| )\]\s*(.+)$/i);
      if (!match) return null;
      return { done: match[1].toLowerCase() === "x", text: match[2].trim() };
    })
    .filter(Boolean);
}

function parseListRows(text) {
  const raw = String(text || "").trim();
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed.map((item) => (typeof item === "string" ? item : JSON.stringify(item)));
    if (parsed && typeof parsed === "object") return Object.entries(parsed).map(([key, value]) => `${key}: ${stringifyBrief(value)}`);
  } catch { /* fallback */ }
  return raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).slice(0, 20);
}

function stringifyBrief(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); } catch { return String(value); }
}

function toTimeValue(value) {
  if (value === null || value === undefined || value === "") return 0;
  if (typeof value === "number") {
    if (value > 1_000_000_000_000) return value;
    if (value > 1_000_000_000) return value * 1000;
    return value;
  }
  const text = String(value).trim();
  if (!text) return 0;
  const asNumber = Number(text);
  if (Number.isFinite(asNumber) && /^\d+(\.\d+)?$/.test(text)) {
    if (asNumber > 1_000_000_000_000) return asNumber;
    if (asNumber > 1_000_000_000) return asNumber * 1000;
  }
  const parsed = Date.parse(text);
  if (!Number.isNaN(parsed)) return parsed;
  return 0;
}

function formatDateTime(value) {
  const ms = toTimeValue(value);
  if (!ms) return "-";
  return new Date(ms).toLocaleString("en-US", {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatTime(value) {
  const ms = toTimeValue(value);
  if (!ms) return "-";
  return new Date(ms).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function formatRelativeTime(value) {
  const ms = toTimeValue(value);
  if (!ms) return "-";
  const delta = Math.max(0, Date.now() - ms);
  const sec = Math.floor(delta / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

function shortSession(sessionId) {
  const value = String(sessionId || "").trim();
  if (!value) return "sess-?";
  if (value.length <= 12) return value;
  return `sess-${value.slice(0, 8)}`;
}

function truncate(text, maxLength) {
  const value = String(text || "");
  if (value.length <= maxLength) return value;
  return `${value.slice(0, Math.max(0, maxLength - 1))}...`;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  const div = document.createElement("div");
  div.textContent = String(value);
  return div.innerHTML;
}

function cssEscape(value) {
  const text = String(value || "");
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") {
    return CSS.escape(text);
  }
  return text.replace(/["\\]/g, "\\$&");
}

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}
