const THREAD_PAGE_SIZE = 5;
const THREAD_REFRESH_MS = 15000;
const TOOL_PREVIEW_LIMIT = 360;
const INITIAL_EVENT_LIMIT = 120;
const OLDER_EVENT_LIMIT = 120;
const RENDER_CHUNK_SIZE = 28;

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
  startThreadPolling();
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
          selectThread(threadId, { preferredSessionId: sessionId }).catch((error) => {
            console.error("Thread change failed", error);
          });
          setMobileDrawerOpen(false);
          return;
        }

        selectSession(sessionId).catch((error) => {
          console.error("Session select failed", error);
        });
        setMobileDrawerOpen(false);
        return;
      }

      const threadCard = event.target.closest("[data-thread-id]");
      if (!threadCard) return;
      const threadId = threadCard.getAttribute("data-thread-id");
      if (!threadId) return;
      selectThread(threadId).catch((error) => {
        console.error("Thread select failed", error);
      });
      setMobileDrawerOpen(false);
    });
  }

  if (el.sessionTopology) {
    el.sessionTopology.addEventListener("click", (event) => {
      const node = event.target.closest("[data-session-id]");
      if (!node) return;
      const sessionId = node.getAttribute("data-session-id");
      if (!sessionId) return;
      selectSession(sessionId).catch((error) => {
        console.error("Session select from topology failed", error);
      });
    });
  }

  if (el.threadsPrev) {
    el.threadsPrev.addEventListener("click", () => {
      if (state.threadMeta.page <= 1) return;
      state.threadMeta.page -= 1;
      refreshThreads({ preserveSelection: true, loadSelected: true, allowPageSearch: false }).catch(
        (error) => {
          console.error("Thread prev page failed", error);
        },
      );
    });
  }

  if (el.threadsNext) {
    el.threadsNext.addEventListener("click", () => {
      if (state.threadMeta.totalPages && state.threadMeta.page >= state.threadMeta.totalPages) {
        return;
      }
      state.threadMeta.page += 1;
      refreshThreads({ preserveSelection: true, loadSelected: true, allowPageSearch: false }).catch(
        (error) => {
          console.error("Thread next page failed", error);
        },
      );
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

    el.streamPane.addEventListener("scroll", () => {
      maybeLoadOlderEvents().catch((error) => {
        console.warn("Older event load failed", error);
      });
    });
  }

  if (el.composerInput) {
    el.composerInput.addEventListener("input", () => {
      renderComposer();
    });

    el.composerInput.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey) return;
      event.preventDefault();
      submitComposer().catch((error) => {
        console.error("Composer submit failed", error);
      });
    });
  }

  if (el.composerSend) {
    el.composerSend.addEventListener("click", () => {
      submitComposer().catch((error) => {
        console.error("Composer send failed", error);
      });
    });
  }

  if (el.terminateSessionBtn) {
    el.terminateSessionBtn.addEventListener("click", () => {
      terminateSelectedSession().catch((error) => {
        console.error("Terminate session failed", error);
      });
    });
  }

  window.addEventListener("resize", () => {
    if (!isDrawerMode()) {
      setMobileDrawerOpen(false);
    }
  });
}

function startThreadPolling() {
  if (state.threadPollTimer) {
    clearInterval(state.threadPollTimer);
  }

  state.threadPollTimer = setInterval(() => {
    refreshThreads({ preserveSelection: true, loadSelected: false, allowPageSearch: true }).catch(
      (error) => {
        console.warn("Thread poll failed", error);
      },
    );
  }, THREAD_REFRESH_MS);
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

  if (
    preserveSelection &&
    previousSelected &&
    !nextMap.has(previousSelected) &&
    allowPageSearch &&
    state.threadMeta.totalPages > 1
  ) {
    const foundPage = await findThreadPage(previousSelected, state.threadMeta.totalPages);
    if (foundPage && foundPage !== state.threadMeta.page) {
      state.threadMeta.page = foundPage;
      await refreshThreads({ preserveSelection, loadSelected, allowPageSearch: false });
      return;
    }
  }

  if (!preserveSelection || !previousSelected || !nextMap.has(previousSelected)) {
    state.selectedThreadId = nextOrder[0] || null;
  }

  renderThreadList();
  renderThreadPagination();

  if (!state.selectedThreadId) {
    setThreadLoading(null, false);
    closeThreadStream();
    renderHeader();
    renderTopology();
    renderStreamFull({ progressive: false });
    return;
  }

  if (loadSelected) {
    await loadThreadSessions(state.selectedThreadId, { forceReload: true });
    connectThreadStream(state.selectedThreadId);
  } else {
    renderHeader();
  }
}

async function findThreadPage(threadId, totalPages) {
  for (let page = 1; page <= totalPages; page += 1) {
    const payload = await fetchJson(`/api/threads?page=${page}&page_size=${THREAD_PAGE_SIZE}`);
    const threads = Array.isArray(payload?.threads) ? payload.threads : [];
    if (threads.some((thread) => String(thread.thread_id || "") === threadId)) {
      return page;
    }
  }
  return null;
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

  connectThreadStream(threadId);
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

async function maybeLoadOlderEvents() {
  const sessionId = state.selectedSessionId;
  if (!sessionId || !el.streamPane) return;
  if (state.loadingSessionId === sessionId) return;
  if (el.streamPane.scrollTop > 80) return;

  const range = state.sessionRangeById.get(sessionId);
  if (!range || !range.hasOlder || !range.minSeq || range.minSeq === Number.MAX_SAFE_INTEGER) {
    return;
  }
  if (state.loadingOlderBySession.has(sessionId)) return;

  state.loadingOlderBySession.add(sessionId);
  const prevHeight = el.streamPane.scrollHeight;
  const prevTop = el.streamPane.scrollTop;

  try {
    await loadSessionWorktree(sessionId, {
      replace: false,
      preferCache: false,
      limit: OLDER_EVENT_LIMIT,
      showLoading: false,
      beforeSeq: range.minSeq,
    });

    await nextFrame();
    const newHeight = el.streamPane.scrollHeight;
    el.streamPane.scrollTop = Math.max(0, newHeight - prevHeight + prevTop);
  } finally {
    state.loadingOlderBySession.delete(sessionId);
  }
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

  el.breadcrumbSession.textContent = `${shortSession(session.session_id)} · ${truncate(
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
  const message = String(el.composerInput.value || "").trim();

  el.composerInput.disabled = state.composerBusy || !hasThread;
  el.composerInput.placeholder = hasThread
    ? "Enter a message to start a new parallel session within this thread. (Enter to send, Shift+Enter for newline)"
    : "Select a thread from the Threads panel first.";

  el.composerSend.disabled = state.composerBusy || !hasThread || !message;
  adjustComposerHeight();
}

function renderSessionActions() {
  renderComposer();

  if (!el.terminateSessionBtn) return;
  const session = getSelectedSession();
  const status = normalizeStatus(session?.status);
  const isTerminal = status === "completed" || status === "failed" || status === "cancelled";
  const isTerminating = Boolean(session && state.terminatingSessionId === session.session_id);

  el.terminateSessionBtn.disabled = !session || isTerminal || isTerminating;
  el.terminateSessionBtn.textContent = isTerminating ? "Terminating..." : "Terminate";
}

async function submitComposer() {
  if (state.composerBusy) return;
  const thread = getSelectedThread();
  const threadId = state.selectedThreadId;
  if (!thread || !threadId || !el.composerInput) return;

  const message = String(el.composerInput.value || "").trim();
  if (!message) {
    renderComposer();
    return;
  }

  state.composerBusy = true;
  renderSessionActions();

  try {
    const payload = await fetchJson(
      `/api/threads/${encodeURIComponent(thread.channel_id)}/${encodeURIComponent(thread.thread_ts)}/sessions`,
      {
        method: "POST",
        body: JSON.stringify({
          message,
          user_id: "dashboard_user",
          run_executor: "claude",
        }),
      },
    );

    el.composerInput.value = "";
    adjustComposerHeight();

    const createdSessionId = String(payload?.session?.session_id || "");
    await loadThreadSessions(threadId, {
      forceReload: true,
      preferredSessionId: createdSessionId || null,
    });
  } finally {
    state.composerBusy = false;
    renderSessionActions();
  }
}

async function terminateSelectedSession() {
  const thread = getSelectedThread();
  const session = getSelectedSession();
  const threadId = state.selectedThreadId;
  if (!thread || !session || !threadId) return;

  const sessionId = String(session.session_id || "");
  if (!sessionId || state.terminatingSessionId === sessionId) return;

  state.terminatingSessionId = sessionId;
  renderSessionActions();

  try {
    const payload = await fetchJson(
      `/api/threads/${encodeURIComponent(thread.channel_id)}/${encodeURIComponent(thread.thread_ts)}/sessions/${encodeURIComponent(sessionId)}/terminate`,
      {
        method: "POST",
        body: JSON.stringify({
          reason: "terminated_by_user",
          force: true,
        }),
      },
    );

    const localSession = getSessionById(threadId, sessionId);
    if (localSession) {
      localSession.status = String(payload?.status || localSession.status || "cancelled");
      localSession.updated_at = new Date().toISOString();
    }

    renderThreadList();
    renderTopology();
    renderHeader();

    await loadSessionWorktree(sessionId, {
      replace: true,
      preferCache: false,
      limit: INITIAL_EVENT_LIMIT,
      showLoading: false,
      beforeSeq: 0,
    });
  } finally {
    state.terminatingSessionId = null;
    renderSessionActions();
  }
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
    el.sessionTopology.innerHTML = new Array(4)
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
      const fullTitle = cleanTopologyText(
        session.request_full || session.request_preview || session.summary || "Session",
      );
      const tooltipText = fullTitle || "Session";

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

function isNarrowMobile() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(max-width: 640px)").matches
  );
}

function isTopologyNodeVisible(container, node) {
  const containerRect = container.getBoundingClientRect();
  const nodeRect = node.getBoundingClientRect();

  const inset = 2;
  const fitsVertically =
    nodeRect.top >= containerRect.top + inset && nodeRect.bottom <= containerRect.bottom - inset;
  const fitsHorizontally =
    nodeRect.left >= containerRect.left + inset && nodeRect.right <= containerRect.right - inset;

  return fitsVertically && fitsHorizontally;
}

function ensureTopologySelectionVisible(sessionId) {
  if (!el.sessionTopology || !sessionId) return;

  const target = el.sessionTopology.querySelector(
    `.topology-node[data-session-id="${cssEscape(sessionId)}"]`,
  );
  if (!target || isTopologyNodeVisible(el.sessionTopology, target)) return;

  const options = isNarrowMobile()
    ? { block: "nearest", inline: "nearest", behavior: "auto" }
    : { block: "nearest", inline: "center", behavior: "auto" };

  target.scrollIntoView(options);
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

  if (progressive) {
    progressiveRenderBlockList(sessionId, blocks).catch((error) => {
      console.error("Progressive render failed", error);
      renderBlockListSync(sessionId, blocks);
    });
  } else {
    renderBlockListSync(sessionId, blocks);
  }

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

async function progressiveRenderBlockList(sessionId, blocks) {
  el.streamList.innerHTML = "";

  const chunks = [];
  for (let i = 0; i < blocks.length; i += RENDER_CHUNK_SIZE) {
    chunks.push(blocks.slice(i, i + RENDER_CHUNK_SIZE));
  }

  const ui = getSessionUiState(sessionId);
  let rendered = 0;
  for (const chunk of chunks) {
    if (state.selectedSessionId !== sessionId) {
      return;
    }

    const html = chunk
      .map((block, idx) => {
        const absoluteIndex = rendered + idx;
        const isLast = absoluteIndex === blocks.length - 1;
        return renderStreamBlock(block, {
          animate: false,
          last: isLast,
          sessionUi: ui,
        });
      })
      .join("");

    el.streamList.insertAdjacentHTML("beforeend", html);
    rendered += chunk.length;
    await nextFrame();
  }
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
      if (ui.collapseToolsOnly) {
        return;
      }

      if (kind === "tool_result") {
        const parentGroupId = String(event.tool_use_id || event.parent_event_id || "");
        const hasCall = groups.some((group) => group.groupId === parentGroupId && group.call);
        if (hasCall) {
          return;
        }
      }

      const group = groupedToolBySeq.get(seq);
      if (group) {
        blocks.push({
          type: "tool",
          event,
          group,
        });
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

    if (groupedToolIds.has(String(event.event_id || ""))) {
      return;
    }

    blocks.push({
      type: "event",
      event,
    });
  });

  return blocks;
}

function renderStreamBlock(block, { animate, last, sessionUi }) {
  if (block.type === "tool") {
    return renderToolTimelineItem(block.group, {
      animate,
      last,
      sessionUi,
    });
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
  const renderedOutput = renderToolOutput(
    name,
    family,
    result,
    expanded,
    TOOL_PREVIEW_LIMIT,
  );

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

function appendEventToUi(sessionId, event) {
  const nearBottom = isNearBottom(el.streamPane);
  const events = state.eventsBySession.get(sessionId) || [];
  const { pinnedIds } = getPinnedEvents(events);

  if (sessionId === state.selectedSessionId) {
    renderPinnedEvents(sessionId, events);
  }

  if (pinnedIds.has(String(event.event_id || ""))) {
    return;
  }

  renderStreamControls(events, sessionId);
  const ui = getSessionUiState(sessionId);

  if (
    isToolEvent(event.kind) && ui.collapseToolsOnly
  ) {
    return;
  }

  if (isToolEvent(event.kind)) {
    const groupId = String(event.tool_use_id || event.parent_event_id || event.event_id || "");
    const groups = buildToolGroups(events);
    const group = groups.find((item) => item.groupId === groupId);
    if (!group || !el.streamList) return;

    const existing = el.streamList.querySelector(
      `[data-tool-group-id="${cssEscape(group.groupId || "")}"]`,
    );
    const rendered = renderToolTimelineItem(group, {
      animate: true,
      last: false,
      sessionUi: ui,
    });

    if (existing) {
      existing.outerHTML = rendered;
    } else {
      insertEventAtCorrectPosition(event, rendered);
    }
  } else {
    if (el.streamList) {
      const rendered = renderEventCard(event, {
        animate: true,
        last: false,
      });
      insertEventAtCorrectPosition(event, rendered);
    }
  }

  const items = el.streamList ? [...el.streamList.querySelectorAll(".timeline-item")] : [];
  items.forEach((node, index) => {
    node.classList.toggle("last", index === items.length - 1);
  });

  if (nearBottom) {
    scrollToBottom(el.streamPane);
  }

  el.emptyState.style.display = "none";
}

function insertEventAtCorrectPosition(event, rendered) {
  if (!el.streamList) return;

  const eventSeq = Number(event.seq || 0);
  const existingItems = [...el.streamList.querySelectorAll(".timeline-item[data-seq]")];

  // Find the first item with seq greater than this event's seq
  let insertBefore = null;
  for (const item of existingItems) {
    const itemSeq = Number(item.dataset.seq || 0);
    if (itemSeq > eventSeq) {
      insertBefore = item;
      break;
    }
  }

  // Remove any existing 'last' class
  const existingLast = el.streamList.querySelector(".timeline-item.last");
  if (existingLast) existingLast.classList.remove("last");

  if (insertBefore) {
    // Insert before the found element
    insertBefore.insertAdjacentHTML("beforebegin", rendered);
  } else {
    // Append at the end
    el.streamList.insertAdjacentHTML("beforeend", rendered);
  }
}

function connectThreadStream(threadId) {
  const thread = state.threadsById.get(threadId);
  if (!thread) return;

  if (state.sse && state.sseThreadId === threadId) {
    return;
  }

  closeThreadStream();

  const url = `/api/threads/${encodeURIComponent(thread.channel_id)}/${encodeURIComponent(
    thread.thread_ts,
  )}/stream`;
  const source = new EventSource(url);
  state.sse = source;
  state.sseThreadId = threadId;

  source.addEventListener("open", () => {
    setConnectionBadge(true);
  });

  source.addEventListener("session_added", (payload) => {
    const session = parseSseData(payload);
    if (!session || !session.session_id) return;
    handleSessionAdded(threadId, session);
  });

  source.addEventListener("session_updated", (payload) => {
    const session = parseSseData(payload);
    if (!session || !session.session_id) return;
    handleSessionUpdated(threadId, session);
  });

  source.addEventListener("event_added", (payload) => {
    const data = parseSseData(payload);
    if (!data || !data.session_id || !data.event) return;
    handleEventAdded(threadId, data.session_id, data.event);
  });

  source.addEventListener("heartbeat", () => {
    setConnectionBadge(true);
  });

  source.onerror = () => {
    setConnectionBadge(false);
  };
}

function closeThreadStream() {
  if (state.sse) {
    state.sse.close();
  }
  state.sse = null;
  state.sseThreadId = null;
}

function handleSessionAdded(threadId, session) {
  const list = state.sessionsByThread.get(threadId) || [];
  const exists = list.some((item) => item.session_id === session.session_id);
  if (!exists) {
    list.push(session);
    list.sort((a, b) => toTimeValue(a.created_at) - toTimeValue(b.created_at));
    state.sessionsByThread.set(threadId, list);
  }

  const thread = state.threadsById.get(threadId);
  if (thread) {
    thread.session_count = list.length;
    thread.live_session_count = list.filter((item) => isLiveStatus(item.status)).length;
    thread.latest_session_id = list[list.length - 1]?.session_id || thread.latest_session_id;
    thread.updated_at = list[list.length - 1]?.updated_at || thread.updated_at;
    state.threadsById.set(threadId, thread);
  }

  renderThreadList();
  renderTopology();
  renderHeader();

  if (!state.selectedSessionId && threadId === state.selectedThreadId) {
    selectSession(session.session_id).catch((error) => {
      console.error("Auto-select new session failed", error);
    });
  }
}

function handleSessionUpdated(threadId, session) {
  const list = state.sessionsByThread.get(threadId) || [];
  const index = list.findIndex((item) => item.session_id === session.session_id);
  if (index >= 0) {
    list[index] = {
      ...list[index],
      ...session,
    };
  } else {
    list.push(session);
  }
  list.sort((a, b) => toTimeValue(a.created_at) - toTimeValue(b.created_at));
  state.sessionsByThread.set(threadId, list);

  const thread = state.threadsById.get(threadId);
  if (thread) {
    thread.live_session_count = list.filter((item) => isLiveStatus(item.status)).length;
    thread.latest_session_id = list[list.length - 1]?.session_id || thread.latest_session_id;
    thread.updated_at = list[list.length - 1]?.updated_at || thread.updated_at;
    state.threadsById.set(threadId, thread);
  }

  renderThreadList();
  renderTopology();
  renderHeader();
}

function handleEventAdded(threadId, sessionId, event) {
  const eventId = String(event.event_id || "");
  if (!eventId) return;

  const seen = state.eventIdsBySession.get(sessionId) || new Set();
  if (seen.has(eventId)) return;

  seen.add(eventId);
  state.eventIdsBySession.set(sessionId, seen);

  const events = state.eventsBySession.get(sessionId) || [];
  events.push(event);
  events.sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));
  state.eventsBySession.set(sessionId, events);

  const currentCursor = Number(state.sessionCursorById.get(sessionId) || 0);
  state.sessionCursorById.set(sessionId, Math.max(currentCursor, Number(event.seq || 0)));

  const sessionRange = state.sessionRangeById.get(sessionId) || {
    minSeq: Number(event.seq || 0),
    maxSeq: Number(event.seq || 0),
    hasOlder: false,
    totalEvents: events.length,
  };
  sessionRange.minSeq = Math.min(sessionRange.minSeq || Number.MAX_SAFE_INTEGER, Number(event.seq || 0));
  sessionRange.maxSeq = Math.max(sessionRange.maxSeq || 0, Number(event.seq || 0));
  sessionRange.totalEvents = Math.max(Number(sessionRange.totalEvents || 0), events.length);
  state.sessionRangeById.set(sessionId, sessionRange);

  touchSessionCountsByIncomingEvent(threadId, sessionId, event);

  if (threadId === state.selectedThreadId && sessionId === state.selectedSessionId) {
    if (state.loadingSessionId !== sessionId) {
      appendEventToUi(sessionId, event);
      renderHeader();
    }
  } else {
    renderThreadList();
    renderTopology();
  }
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
  session.updated_at = events[events.length - 1]?.ts || session.updated_at;

  session.status = deriveSessionStatusFromEvents(session.status, events);

  renderThreadList();
  renderTopology();
}

function touchSessionCountsByIncomingEvent(threadId, sessionId, event) {
  const session = getSessionById(threadId, sessionId);
  if (!session) return;

  session.event_count = Number(session.event_count || 0) + 1;
  session.event_counts = session.event_counts || {
    thinking: 0,
    tool_call: 0,
    tool_result: 0,
    output: 0,
  };

  if (event.kind === "assistant_thinking") session.event_counts.thinking += 1;
  if (event.kind === "tool_call") session.event_counts.tool_call += 1;
  if (event.kind === "tool_result") session.event_counts.tool_result += 1;
  if (event.kind === "assistant_output") session.event_counts.output += 1;

  session.updated_at = event.ts || session.updated_at;

  const currentEvents = state.eventsBySession.get(sessionId) || [];
  session.status = deriveSessionStatusFromEvents(session.status, currentEvents);

  renderThreadList();
  renderTopology();
}

function deriveSessionStatusFromEvents(currentStatus, events) {
  const normalized = normalizeStatus(currentStatus);
  if (normalized && normalized !== "pending") {
    return normalized;
  }
  if (!events.length) return "pending";

  if (events.some((event) => event.kind === "tool_result" && normalizeStatus(event.status) === "failed")) {
    return "failed";
  }

  const last = events[events.length - 1];
  if (last.kind === "tool_call" || normalizeStatus(last.status) === "active") {
    return "active";
  }
  if (last.kind === "assistant_output") {
    return "completed";
  }
  return "active";
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

function parseSseData(messageEvent) {
  try {
    return JSON.parse(messageEvent.data);
  } catch {
    return null;
  }
}

function isToolEvent(kind) {
  return kind === "tool_call" || kind === "tool_result";
}

function isLiveStatus(status) {
  const normalized = normalizeStatus(status);
  return normalized === "active" || normalized === "waiting";
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
    case "user_command":
      return "User Command";
    case "assistant_thinking":
      return "Thinking";
    case "assistant_observation":
      return "Observation";
    case "assistant_output":
      return "Assistant Output";
    default:
      return kind || "Event";
  }
}

function iconForKind(kind) {
  switch (kind) {
    case "user_command":
      return "solar:user-bold";
    case "assistant_thinking":
      return "solar:lightbulb-minimalistic-bold";
    case "assistant_observation":
      return "solar:telescope-bold";
    case "assistant_output":
      return "solar:chat-square-bold";
    default:
      return "solar:stars-bold";
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
  if (["read", "edit", "write"].some((token) => name === token || name.endsWith(`_${token}`))) {
    return "file";
  }
  if (["grep", "glob", "toolsearch"].some((token) => name.includes(token))) return "list";
  if (["webfetch", "websearch"].some((token) => name.includes(token))) return "web";
  if (name.includes("todowrite")) return "todo";
  if (name.startsWith("mcp__slack") || name.startsWith("mcp__slack-bot")) return "slack";
  if (
    name.startsWith("mcp__playwright") ||
    name.startsWith("mcp__browsermcp") ||
    name.startsWith("mcp__puppeteer")
  ) {
    return "browser";
  }

  return "generic";
}

function iconForToolFamily(family) {
  switch (family) {
    case "bash":
      return "solar:terminal-2-bold";
    case "file":
      return "solar:file-code-bold";
    case "slack":
      return "solar:hashtag-square-bold";
    case "web":
      return "solar:global-bold";
    case "todo":
      return "solar:checklist-minimalistic-bold";
    case "browser":
      return "solar:window-frame-bold";
    case "list":
      return "solar:list-check-bold";
    default:
      return "solar:code-square-bold";
  }
}

function extractToolResultText(resultEvent) {
  if (!resultEvent) return "";

  const raw = resultEvent.raw || {};
  const rawContent = raw.content;
  if (typeof rawContent === "string") {
    return rawContent;
  }
  if (Array.isArray(rawContent)) {
    const parts = rawContent
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object") {
          if (typeof part.text === "string") return part.text;
          try {
            return JSON.stringify(part, null, 2);
          } catch {
            return String(part);
          }
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length) {
      return parts.join("\n");
    }
  }

  if (rawContent && typeof rawContent === "object") {
    try {
      return JSON.stringify(rawContent, null, 2);
    } catch {
      return String(rawContent);
    }
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
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function parseTodoItems(text) {
  const rows = String(text || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return rows
    .map((line) => {
      const match = line.match(/^[-*]?\s*\[(x| )\]\s*(.+)$/i);
      if (!match) return null;
      return {
        done: match[1].toLowerCase() === "x",
        text: match[2].trim(),
      };
    })
    .filter(Boolean);
}

function parseListRows(text) {
  const raw = String(text || "").trim();
  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.map((item) => (typeof item === "string" ? item : JSON.stringify(item)));
    }
    if (parsed && typeof parsed === "object") {
      return Object.entries(parsed).map(([key, value]) => `${key}: ${stringifyBrief(value)}`);
    }
  } catch {
    // fallback to line split
  }

  return raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 20);
}

function stringifyBrief(value) {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

async function fetchJson(url, options = {}) {
  const headers = {
    Accept: "application/json",
    ...(options.headers || {}),
  };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let reason = "";
    try {
      const payload = await response.json();
      reason = payload?.message || payload?.error || "";
    } catch {
      // no-op
    }
    throw new Error(`HTTP ${response.status}: ${url}${reason ? ` (${reason})` : ""}`);
  }

  return response.json();
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
  return new Date(ms).toLocaleString("ko-KR", {
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
  return new Date(ms).toLocaleTimeString("ko-KR", {
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

function cleanTopologyText(text) {
  let value = String(text || "");
  value = value.replace(/<@[A-Z0-9]+>/g, " ");
  value = value.replace(/<#[A-Z0-9]+\|([^>]+)>/g, "$1");
  value = value.replace(/<([^|>]+)\|([^>]+)>/g, "$2");
  value = value.replace(/<([^>]+)>/g, "$1");
  value = value.replace(/\s+/g, " ").trim();
  return value;
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

function isNearBottom(container) {
  if (!container) return false;
  return container.scrollTop + container.clientHeight >= container.scrollHeight - 90;
}

function scrollToBottom(container) {
  if (!container) return;
  container.scrollTop = container.scrollHeight;
}

function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}
