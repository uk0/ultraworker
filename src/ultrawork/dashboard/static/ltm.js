/**
 * LTM (Long-Term Memory) Visualization Module
 *
 * Provides Notion-like table view and Obsidian-like graph view
 * for browsing RequestRecords and WorkRecords.
 */

/* ── State ── */

const ltmState = {
  records: [],
  graphData: null,
  stats: null,
  selectedRecordId: null,
  currentSubView: "table", // "table" | "graph"
  typeFilter: "all", // "all" | "request" | "work" | "knowledge" | "decision" | "insight" | "event"
  searchQuery: "",
  searchResults: null,
  simulation: null,
  booted: false,
};

/* ── DOM Refs ── */

const ltmEl = {
  tableView: document.getElementById("ltmTableView"),
  graphView: document.getElementById("ltmGraphView"),
  graphSvg: document.getElementById("ltmGraphSvg"),
  detailPanel: document.getElementById("ltmDetailPanel"),
  detailTitle: document.getElementById("ltmDetailTitle"),
  detailBody: document.getElementById("ltmDetailBody"),
  detailClose: document.getElementById("ltmDetailClose"),
  searchInput: document.getElementById("ltmSearchInput"),
  statsBadges: document.getElementById("ltmStatsBadges"),
};

/* ── Boot ── */

function ltmBoot() {
  if (ltmState.booted) return;
  ltmState.booted = true;

  _ltmBindEvents();
  ltmRefresh();
}

function ltmRefresh() {
  Promise.all([_ltmFetchRecords(), _ltmFetchStats()]).then(() => {
    _ltmRender();
  });
}

/* ── Events ── */

function _ltmBindEvents() {
  // Sub-view tabs (Table / Graph)
  document.querySelectorAll(".ltm-tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      const view = btn.getAttribute("data-view");
      if (view === ltmState.currentSubView) return;
      ltmState.currentSubView = view;
      document.querySelectorAll(".ltm-tab").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      _ltmShowSubView(view);
    });
  });

  // Type filter buttons
  document.querySelectorAll(".ltm-type-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const type = btn.getAttribute("data-type");
      ltmState.typeFilter = type;
      document.querySelectorAll(".ltm-type-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      _ltmRender();
    });
  });

  // Search
  if (ltmEl.searchInput) {
    let debounce = null;
    ltmEl.searchInput.addEventListener("input", () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        ltmState.searchQuery = ltmEl.searchInput.value.trim();
        if (ltmState.searchQuery) {
          _ltmSearch(ltmState.searchQuery);
        } else {
          ltmState.searchResults = null;
          _ltmRender();
        }
      }, 300);
    });
  }

  // Detail panel close
  if (ltmEl.detailClose) {
    ltmEl.detailClose.addEventListener("click", _ltmCloseDetail);
  }
}

/* ── Data Fetching ── */

async function _ltmFetchRecords() {
  try {
    const res = await fetch("/api/ltm/records");
    const data = await res.json();
    ltmState.records = data.records || [];
  } catch (e) {
    console.error("LTM records fetch failed", e);
    ltmState.records = [];
  }
}

async function _ltmFetchStats() {
  try {
    const res = await fetch("/api/ltm/stats");
    ltmState.stats = await res.json();
  } catch (e) {
    console.error("LTM stats fetch failed", e);
    ltmState.stats = null;
  }
}

async function _ltmFetchRecordDetail(recordId) {
  try {
    const res = await fetch(`/api/ltm/records/${encodeURIComponent(recordId)}`);
    return await res.json();
  } catch (e) {
    console.error("LTM record detail fetch failed", e);
    return null;
  }
}

async function _ltmFetchGraph() {
  try {
    const res = await fetch("/api/ltm/graph");
    ltmState.graphData = await res.json();
  } catch (e) {
    console.error("LTM graph fetch failed", e);
    ltmState.graphData = null;
  }
}

async function _ltmSearch(query) {
  try {
    const res = await fetch(`/api/ltm/search?q=${encodeURIComponent(query)}&top_k=30`);
    const data = await res.json();
    ltmState.searchResults = data.results || [];
    _ltmRender();
  } catch (e) {
    console.error("LTM search failed", e);
    ltmState.searchResults = null;
    _ltmRender();
  }
}

/* ── Render Orchestration ── */

function _ltmRender() {
  _ltmRenderStats();
  if (ltmState.currentSubView === "table") {
    _ltmRenderTable();
  } else {
    _ltmRenderGraph();
  }
}

function _ltmShowSubView(view) {
  if (view === "table") {
    ltmEl.tableView.style.display = "";
    ltmEl.graphView.style.display = "none";
    _ltmRenderTable();
  } else {
    ltmEl.tableView.style.display = "none";
    ltmEl.graphView.style.display = "";
    _ltmRenderGraph();
  }
}

/* ── Stats Rendering ── */

function _ltmRenderStats() {
  if (!ltmEl.statsBadges || !ltmState.stats) return;
  const s = ltmState.stats;
  ltmEl.statsBadges.innerHTML = `
    <span class="ltm-stat-badge">
      <span class="ltm-stat-num">${s.request_count}</span> REQ
    </span>
    <span class="ltm-stat-badge">
      <span class="ltm-stat-num">${s.work_count}</span> WRK
    </span>
    <span class="ltm-stat-badge">
      <span class="ltm-stat-num">${s.knowledge_count || 0}</span> KNOW
    </span>
    <span class="ltm-stat-badge">
      <span class="ltm-stat-num">${s.decision_count || 0}</span> DEC
    </span>
    <span class="ltm-stat-badge">
      <span class="ltm-stat-num">${s.insight_count || 0}</span> INS
    </span>
    <span class="ltm-stat-badge">
      <span class="ltm-stat-num">${s.event_count || 0}</span> EVT
    </span>
    <span class="ltm-stat-badge">
      <span class="ltm-stat-num">${s.topic_count}</span> topics
    </span>
  `;
}

/* ── Table View ── */

function _ltmRenderTable() {
  if (!ltmEl.tableView) return;

  let records = _ltmFilteredRecords();

  // If search results exist, reorder by search score
  if (ltmState.searchResults) {
    const scoreMap = new Map();
    ltmState.searchResults.forEach((r) => scoreMap.set(r.record_id, r.score));
    const matchedIds = new Set(ltmState.searchResults.map((r) => r.record_id));
    records = records.filter((r) => matchedIds.has(r.id));
    records.sort((a, b) => (scoreMap.get(b.id) || 0) - (scoreMap.get(a.id) || 0));
  }

  if (records.length === 0) {
    ltmEl.tableView.innerHTML = `
      <div class="ltm-empty-state">
        <iconify-icon icon="solar:database-linear" width="40"></iconify-icon>
        <p>${ltmState.searchQuery ? "No records match your search." : "No memory records yet."}</p>
        <p style="font-size:11px;margin-top:4px;opacity:0.7">Records are created when the agent saves to long-term memory.</p>
      </div>
    `;
    return;
  }

  let html = `
    <table class="ltm-table">
      <thead>
        <tr>
          <th style="width:50px">Type</th>
          <th>ID</th>
          <th>Description</th>
          <th>Topics</th>
          <th style="width:60px">Links</th>
          <th style="width:120px">Created</th>
        </tr>
      </thead>
      <tbody>
  `;

  for (const rec of records) {
    const isSelected = rec.id === ltmState.selectedRecordId;
    const isHighlight =
      ltmState.searchResults && ltmState.searchResults.some((r) => r.record_id === rec.id);
    const cls = isSelected ? "ltm-row-selected" : isHighlight ? "ltm-row-highlight" : "";

    const _typeBadgeMap = {
      request: { cls: "type-request", label: "REQ" },
      work: { cls: "type-work", label: "WRK" },
      knowledge: { cls: "type-knowledge", label: "KNOW" },
      decision: { cls: "type-decision", label: "DEC" },
      insight: { cls: "type-insight", label: "INS" },
      event: { cls: "type-event", label: "EVT" },
    };
    const badge = _typeBadgeMap[rec.type] || { cls: "type-request", label: rec.type.toUpperCase() };
    const typeBadge = `<span class="ltm-type-badge ${badge.cls}">${badge.label}</span>`;

    const description =
      rec.type === "request" ? _escHtml(rec.what || "-") : _escHtml(rec.what || rec.purpose || rec.what_summary || "-");

    const topics = (rec.topics || [])
      .slice(0, 4)
      .map((t) => `<span class="ltm-topic-chip">${_escHtml(t)}</span>`)
      .join("");
    const topicsExtra = (rec.topics || []).length > 4 ? `<span class="ltm-topic-chip">+${rec.topics.length - 4}</span>` : "";

    const linkCount = (rec.links_count || 0) + (rec.causality_count || 0);
    const linksBadge = linkCount > 0 ? `<span class="ltm-links-badge">${linkCount}</span>` : "-";

    const created = rec.created_at ? _formatDate(rec.created_at) : "-";

    html += `
      <tr class="${cls}" data-record-id="${_escAttr(rec.id)}" onclick="ltmSelectRecord('${_escAttr(rec.id)}')">
        <td>${typeBadge}</td>
        <td style="font-family:'JetBrains Mono',monospace;font-size:11px">${_escHtml(rec.id)}</td>
        <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${description}</td>
        <td><div class="ltm-topic-chips">${topics}${topicsExtra}</div></td>
        <td style="text-align:center">${linksBadge}</td>
        <td style="font-size:11px;color:var(--ink-soft)">${created}</td>
      </tr>
    `;
  }

  html += "</tbody></table>";
  ltmEl.tableView.innerHTML = html;
}

/* ── Graph View ── */

async function _ltmRenderGraph() {
  if (!ltmEl.graphSvg) return;

  if (!ltmState.graphData) {
    await _ltmFetchGraph();
  }

  const data = ltmState.graphData;
  if (!data || data.node_count === 0) {
    ltmEl.graphView.innerHTML = `
      <div class="ltm-empty-state">
        <iconify-icon icon="solar:graph-new-linear" width="40"></iconify-icon>
        <p>No graph data. Create some memory records first.</p>
      </div>
    `;
    return;
  }

  // Restore SVG if replaced by empty state
  if (!document.getElementById("ltmGraphSvg")) {
    ltmEl.graphView.innerHTML = '<svg id="ltmGraphSvg" width="100%" height="100%"></svg>';
  }

  const svg = d3.select("#ltmGraphSvg");
  svg.selectAll("*").remove();

  const container = ltmEl.graphView;
  const width = container.clientWidth || 800;
  const height = container.clientHeight || 600;

  // Apply type filter to graph
  const filteredNodeIds = new Set();
  let nodes = data.nodes;
  if (ltmState.typeFilter !== "all") {
    nodes = nodes.filter((n) => n.type === ltmState.typeFilter);
  }
  nodes.forEach((n) => filteredNodeIds.add(n.id));

  // Clone nodes/edges for D3 (D3 mutates them)
  const graphNodes = nodes.map((n) => ({ ...n }));
  const graphEdges = data.edges
    .filter((e) => filteredNodeIds.has(e.source) && filteredNodeIds.has(e.target))
    .map((e) => ({ ...e }));

  // Search highlighting
  const searchIds = new Set();
  if (ltmState.searchResults) {
    ltmState.searchResults.forEach((r) => searchIds.add(r.record_id));
  }

  // Create zoom behavior
  const g = svg.append("g");
  const zoom = d3
    .zoom()
    .scaleExtent([0.1, 4])
    .on("zoom", (event) => {
      g.attr("transform", event.transform);
    });
  svg.call(zoom);

  // Force simulation
  if (ltmState.simulation) {
    ltmState.simulation.stop();
  }
  const simulation = d3
    .forceSimulation(graphNodes)
    .force(
      "link",
      d3
        .forceLink(graphEdges)
        .id((d) => d.id)
        .distance(100)
    )
    .force("charge", d3.forceManyBody().strength(-200))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide().radius(30));
  ltmState.simulation = simulation;

  // Draw edges
  const edgeGroup = g
    .selectAll(".graph-edge")
    .data(graphEdges)
    .enter()
    .append("line")
    .attr("class", (d) => {
      const base = "graph-edge";
      if (d.type === "causal") return `${base} graph-edge-causal`;
      if (d.type === "request_ref") return `${base} graph-edge-request-ref`;
      return `${base} graph-edge-shallow`;
    })
    .attr("data-source", (d) => d.source.id || d.source)
    .attr("data-target", (d) => d.target.id || d.target);

  // Draw nodes
  const nodeGroup = g
    .selectAll(".graph-node-g")
    .data(graphNodes)
    .enter()
    .append("g")
    .attr("class", "graph-node-g")
    .call(d3.drag().on("start", _dragStart).on("drag", _dragging).on("end", _dragEnd));

  // Node shapes: circle for requests, rect for works, diamond for semantic
  const _nodeColors = {
    request: "#6d28d9",
    work: "#15803d",
    knowledge: "#1d4ed8",
    decision: "#b45309",
    insight: "#be185d",
    event: "#b91c1c",
  };
  nodeGroup.each(function (d) {
    const el = d3.select(this);
    const isHit = searchIds.size > 0 && searchIds.has(d.id);
    const color = _nodeColors[d.type] || "#6b7280";
    if (d.type === "request") {
      el.append("circle")
        .attr("r", isHit ? 12 : 8)
        .attr("class", "graph-node-req");
    } else if (d.type === "work") {
      const size = isHit ? 20 : 14;
      el.append("rect")
        .attr("width", size)
        .attr("height", size)
        .attr("x", -size / 2)
        .attr("y", -size / 2)
        .attr("rx", 3)
        .attr("class", "graph-node-work");
    } else {
      // Semantic types: diamond shape
      const r = isHit ? 12 : 8;
      el.append("polygon")
        .attr("points", `0,${-r} ${r},0 0,${r} ${-r},0`)
        .attr("fill", color)
        .attr("stroke", "#fff")
        .attr("stroke-width", 1.5)
        .attr("class", "graph-node-semantic");
    }
  });

  // Node labels
  nodeGroup
    .append("text")
    .attr("class", "graph-node-label")
    .attr("dy", 20)
    .text((d) => {
      const label = d.label || d.id;
      return label.length > 20 ? label.substring(0, 20) + "..." : label;
    });

  // Hover behavior
  nodeGroup
    .on("mouseenter", function (event, d) {
      const connectedIds = new Set([d.id]);
      graphEdges.forEach((e) => {
        const sid = typeof e.source === "object" ? e.source.id : e.source;
        const tid = typeof e.target === "object" ? e.target.id : e.target;
        if (sid === d.id) connectedIds.add(tid);
        if (tid === d.id) connectedIds.add(sid);
      });

      container.classList.add("has-hover");

      nodeGroup.each(function (nd) {
        const node = d3.select(this);
        if (connectedIds.has(nd.id)) {
          node.select("circle, rect").classed("graph-node-highlighted", true);
        }
      });

      edgeGroup.each(function (ed) {
        const edge = d3.select(this);
        const sid = typeof ed.source === "object" ? ed.source.id : ed.source;
        const tid = typeof ed.target === "object" ? ed.target.id : ed.target;
        if (sid === d.id || tid === d.id) {
          edge.classed("graph-edge-highlighted", true);
        }
      });
    })
    .on("mouseleave", function () {
      container.classList.remove("has-hover");
      nodeGroup.select("circle, rect").classed("graph-node-highlighted", false);
      edgeGroup.classed("graph-edge-highlighted", false);
    });

  // Click behavior
  nodeGroup.on("click", function (event, d) {
    event.stopPropagation();
    ltmSelectRecord(d.id);
  });

  // Simulation tick
  simulation.on("tick", () => {
    edgeGroup
      .attr("x1", (d) => d.source.x)
      .attr("y1", (d) => d.source.y)
      .attr("x2", (d) => d.target.x)
      .attr("y2", (d) => d.target.y);

    nodeGroup.attr("transform", (d) => `translate(${d.x},${d.y})`);
  });

  // Drag functions
  function _dragStart(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }

  function _dragging(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }

  function _dragEnd(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }
}

/* ── Detail Panel ── */

async function ltmSelectRecord(recordId) {
  ltmState.selectedRecordId = recordId;

  // Highlight table row
  document.querySelectorAll(".ltm-table tbody tr").forEach((tr) => {
    tr.classList.toggle("ltm-row-selected", tr.getAttribute("data-record-id") === recordId);
  });

  // Fetch full detail
  const detail = await _ltmFetchRecordDetail(recordId);
  if (!detail || detail.error) {
    ltmEl.detailTitle.textContent = "Not Found";
    ltmEl.detailBody.innerHTML = `<p style="color:var(--ink-soft)">Record ${_escHtml(recordId)} not found.</p>`;
    ltmEl.detailPanel.classList.add("open");
    return;
  }

  _ltmRenderDetail(detail);
  ltmEl.detailPanel.classList.add("open");
}

function _ltmCloseDetail() {
  ltmState.selectedRecordId = null;
  ltmEl.detailPanel.classList.remove("open");
  document.querySelectorAll(".ltm-table tbody tr.ltm-row-selected").forEach((tr) => {
    tr.classList.remove("ltm-row-selected");
  });
}

function _ltmRenderDetail(detail) {
  const isReq = detail.type === "request";
  const isWork = detail.type === "work";
  const isSemantic = !isReq && !isWork;
  const _badgeMap = {
    request: { cls: "type-request", label: "REQ" },
    work: { cls: "type-work", label: "WRK" },
    knowledge: { cls: "type-knowledge", label: "KNOW" },
    decision: { cls: "type-decision", label: "DEC" },
    insight: { cls: "type-insight", label: "INS" },
    event: { cls: "type-event", label: "EVT" },
  };
  const b = _badgeMap[detail.type] || { cls: "type-request", label: detail.type.toUpperCase() };
  const typeBadge = `<span class="ltm-type-badge ${b.cls}">${b.label}</span>`;

  ltmEl.detailTitle.innerHTML = `${typeBadge} ${_escHtml(detail.id)}`;

  let html = "";

  // Basic info
  html += '<div class="ltm-detail-section">';
  html += '<div class="ltm-detail-section-title">Info</div>';
  html += _detailField("Who", detail.who || "-");
  html += _detailField("When", detail.when ? _formatDate(detail.when) : "-");

  if (isReq) {
    html += _detailField("Where", detail.where || "-");
    html += _detailField("What", detail.what || "-");
  } else if (isWork) {
    html += _detailField("Purpose", detail.purpose || "-");
    html += _detailField("Request", detail.request_ref || "-");
    html += _detailField("Step", detail.step_ref || "-");
    html += _detailField("Actions", detail.what_summary || "-");
  } else {
    // Semantic record
    if (detail.where) html += _detailField("Where", detail.where);
    html += _detailField("What", detail.what || "-");
    if (detail.source) html += _detailField("Source", detail.source);
    if (detail.period) html += _detailField("Period", detail.period);
    if (detail.severity) html += _detailField("Severity", detail.severity);
  }
  html += "</div>";

  // Topics
  if (detail.topics && detail.topics.length > 0) {
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Topics</div>';
    html += '<div class="ltm-topic-chips">';
    detail.topics.forEach((t) => {
      html += `<span class="ltm-topic-chip">${_escHtml(t)}</span>`;
    });
    html += "</div></div>";
  }

  // How steps (request only)
  if (isReq && detail.how && detail.how.length > 0) {
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Intent Steps</div>';
    html += '<div class="ltm-step-list">';
    detail.how.forEach((step) => {
      const checkCls = step.done ? "done" : "pending";
      const icon = step.done ? "&#10003;" : "&#9675;";
      html += `
        <div class="ltm-step-item">
          <span class="ltm-step-check ${checkCls}">${icon}</span>
          <span>${_escHtml(step.step_id)}: ${_escHtml(step.goal)}</span>
        </div>
      `;
    });
    html += "</div></div>";
  }

  // What actions (work only)
  if (!isReq && detail.what_actions && detail.what_actions.length > 0) {
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Actions</div>';
    detail.what_actions.forEach((a) => {
      html += `<div style="font-size:12px;margin-bottom:4px">${_escHtml(a.action)}</div>`;
      if (a.output) {
        html += `<div style="font-size:11px;color:var(--ink-soft);margin-left:8px">${_escHtml(a.output)}</div>`;
      }
    });
    html += "</div>";
  }

  // Causal links
  const causalLinks = isReq ? detail.causality : detail.why_detail ? detail.why_detail.causality : [];
  if (causalLinks && causalLinks.length > 0) {
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Causal Chain</div>';
    html += '<div class="ltm-causal-chain">';
    causalLinks.forEach((cl) => {
      const relClass = "rel-" + cl.relation.replace(/_/g, "-");
      html += `
        <div class="ltm-causal-item" onclick="ltmSelectRecord('${_escAttr(cl.target_id)}')">
          <span class="ltm-causal-relation ${relClass}">${_escHtml(cl.relation)}</span>
          <span class="ltm-causal-arrow">&rarr;</span>
          <span style="font-family:'JetBrains Mono',monospace;font-size:11px">${_escHtml(cl.target_id)}</span>
          ${cl.reason ? `<span style="color:var(--ink-soft);font-size:10px">${_escHtml(cl.reason)}</span>` : ""}
        </div>
      `;
    });
    html += "</div></div>";
  }

  // Shallow links
  if (detail.links && detail.links.length > 0) {
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Linked Records</div>';
    html += '<div class="ltm-linked-records">';
    detail.links.forEach((ln) => {
      html += `
        <div class="ltm-linked-record" onclick="ltmSelectRecord('${_escAttr(ln.target_id)}')">
          <span style="color:var(--ink-soft);font-size:10px">${_escHtml(ln.relation)}</span>
          <span style="font-family:'JetBrains Mono',monospace;font-size:11px">${_escHtml(ln.target_id)}</span>
        </div>
      `;
    });
    html += "</div></div>";
  }

  // File paths (work only)
  if (!isReq) {
    const inputs = detail.inputs || [];
    const outputs = detail.outputs || [];
    if (inputs.length > 0 || outputs.length > 0) {
      html += '<div class="ltm-detail-section">';
      html += '<div class="ltm-detail-section-title">Files</div>';
      if (inputs.length > 0) {
        html += '<div style="font-size:11px;color:var(--ink-soft);margin-bottom:2px">Inputs:</div>';
        inputs.forEach((f) => {
          html += `<div style="font-size:11px;font-family:'JetBrains Mono',monospace">${_escHtml(f)}</div>`;
        });
      }
      if (outputs.length > 0) {
        html += '<div style="font-size:11px;color:var(--ink-soft);margin-bottom:2px;margin-top:4px">Outputs:</div>';
        outputs.forEach((f) => {
          html += `<div style="font-size:11px;font-family:'JetBrains Mono',monospace">${_escHtml(f)}</div>`;
        });
      }
      html += "</div>";
    }
  }

  // Save signals
  if (detail.save_signals) {
    const ss = detail.save_signals;
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Save Signals</div>';
    html += '<div class="ltm-signals">';
    ["novelty", "actionability", "persistence", "connectedness"].forEach((sig) => {
      const on = ss[sig];
      html += `<span class="ltm-signal ${on ? "signal-on" : "signal-off"}">${on ? "&#10003;" : "&#10007;"} ${sig}</span>`;
    });
    html += `<span class="ltm-signal signal-on" style="font-weight:600">${ss.score}/4</span>`;
    html += "</div></div>";
  }

  // Facet keys
  if (detail.facet_keys && detail.facet_keys.length > 0) {
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Facet Keys</div>';
    html += '<div class="ltm-topic-chips">';
    detail.facet_keys.forEach((k) => {
      html += `<span class="ltm-topic-chip" style="background:#f1f5f9;color:var(--ink-soft)">${_escHtml(k)}</span>`;
    });
    html += "</div></div>";
  }

  // Semantic-specific fields
  if (isSemantic) {
    const textFields = [
      ["summary", "Summary"], ["context", "Context"], ["rationale", "Rationale"],
      ["outcome", "Outcome"], ["pattern", "Pattern"], ["implication", "Implication"],
      ["impact", "Impact"], ["resolution", "Resolution"],
    ];
    for (const [key, label] of textFields) {
      if (detail[key]) {
        html += '<div class="ltm-detail-section">';
        html += `<div class="ltm-detail-section-title">${label}</div>`;
        html += `<div style="font-size:12px;white-space:pre-wrap">${_escHtml(detail[key])}</div>`;
        html += "</div>";
      }
    }
    if (detail.alternatives && detail.alternatives.length > 0) {
      html += '<div class="ltm-detail-section">';
      html += '<div class="ltm-detail-section-title">Alternatives</div>';
      detail.alternatives.forEach((a) => {
        html += `<div style="font-size:12px">- ${_escHtml(a)}</div>`;
      });
      html += "</div>";
    }
    if (detail.evidence && detail.evidence.length > 0) {
      html += '<div class="ltm-detail-section">';
      html += '<div class="ltm-detail-section-title">Evidence</div>';
      detail.evidence.forEach((e) => {
        html += `<div style="font-size:12px">- ${_escHtml(e)}</div>`;
      });
      html += "</div>";
    }
  }

  // Body content
  if (detail.body && detail.body.trim()) {
    html += '<div class="ltm-detail-section">';
    html += '<div class="ltm-detail-section-title">Body</div>';
    html += `<div class="ltm-body-content">${_escHtml(detail.body)}</div>`;
    html += "</div>";
  }

  ltmEl.detailBody.innerHTML = html;
}

/* ── Helpers ── */

function _ltmFilteredRecords() {
  if (ltmState.typeFilter === "all") return ltmState.records;
  return ltmState.records.filter((r) => r.type === ltmState.typeFilter);
}

function _detailField(label, value) {
  return `
    <div class="ltm-detail-field">
      <span class="ltm-detail-field-label">${_escHtml(label)}</span>
      <span class="ltm-detail-field-value">${_escHtml(value)}</span>
    </div>
  `;
}

function _escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _escAttr(str) {
  return _escHtml(str).replace(/'/g, "&#39;");
}

function _formatDate(isoStr) {
  if (!isoStr) return "-";
  try {
    const d = new Date(isoStr);
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hours = String(d.getHours()).padStart(2, "0");
    const mins = String(d.getMinutes()).padStart(2, "0");
    return `${month}-${day} ${hours}:${mins}`;
  } catch {
    return isoStr.substring(0, 16);
  }
}
