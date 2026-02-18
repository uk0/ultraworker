/**
 * Agent Tree Flow Component
 * Tree-based visualization for agent tool calling interactions
 */

class AgentTreeFlow {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      console.error(`Container #${containerId} not found`);
      return;
    }

    this.options = {
      emptyMessage: "Select a thread to view the Agent Flow.",
      ...options,
    };

    this.events = [];
    this.tree = [];
    this.eventMap = new Map();
    this.collapsedNodes = new Set();
    this.onSelect = null;

    this.handleClick = this.handleClick.bind(this);
    this.container.addEventListener("click", this.handleClick);
  }

  setEvents(events = [], meta = {}) {
    this.events = Array.isArray(events) ? events : [];
    this.meta = meta || {};
    this.eventMap.clear();
    this.tree = this.buildTree(this.events);
    this.render();
  }

  clear() {
    this.setEvents([]);
  }

  /**
   * Build tree structure from flat event list
   * User Request -> Agent Thought -> Tool Execution
   */
  buildTree(events) {
    const tree = [];
    const eventList = Array.isArray(events) ? events : [];
    const requestList = Array.isArray(this.meta?.requests) ? this.meta.requests : [];

    const requestBySession = new Map();
    requestList.forEach((req, idx) => {
      const sessionId = req.log_session_id || req.session_id || req.sessionId;
      if (!sessionId) return;
      requestBySession.set(sessionId, { req, idx });
    });

    const groups = new Map();

    eventList.forEach((event) => {
      const sessionId = event.sessionId || 'unknown';
      if (!groups.has(sessionId)) {
        const requestEntry = requestBySession.get(sessionId);
        groups.set(sessionId, {
          sessionId,
          req: requestEntry?.req || null,
          idx: requestEntry?.idx ?? groups.size,
          events: [],
        });
      }
      groups.get(sessionId).events.push(event);
    });

    if (groups.size === 0) {
      requestList.forEach((req, idx) => {
        const sessionId = req.log_session_id || req.session_id || req.sessionId;
        if (!sessionId) return;
        if (!groups.has(sessionId)) {
          groups.set(sessionId, { sessionId, req, idx, events: [] });
        }
      });
    }

    const groupEntries = Array.from(groups.values());
    groupEntries.sort((a, b) => this.resolveGroupSort(a, b));

    groupEntries.forEach((group, idx) => {
      const requestNode = this.buildRequestNode(group, idx);
      if (!requestNode) return;

      const orderedEvents = group.events.slice().sort((a, b) => {
        const at = a.timestamp ?? Infinity;
        const bt = b.timestamp ?? Infinity;
        if (at === bt) return (a.order ?? 0) - (b.order ?? 0);
        return at - bt;
      });

      orderedEvents.forEach((event, eventIdx) => {
        const thoughtText = this.buildThoughtText(event);
        const thoughtNode = this.createGroupNode({
          id: `thought-${event.id || `${group.sessionId}-${eventIdx}`}`,
          title: `Thinking · ${thoughtText}`,
          summary: '',
          category: event.category || '',
          categoryLabel: event.categoryLabel || '',
          lane: 'agent',
          status: event.status || 'complete',
          timestamp: event.timestamp,
          timeLabel: event.timeLabel,
          sessionId: event.sessionId,
          inputData: { thought: thoughtText, category: event.categoryLabel || event.category || '' },
          description: thoughtText,
        });

        const toolNode = this.createNode({
          ...event,
          title: `Tool Execution · ${event.toolLabel || event.title || event.tool || 'Tool'}`,
          summary: '',
          lane: 'tool',
        });

        thoughtNode.children.push(toolNode);
        requestNode.children.push(thoughtNode);
      });

      if (!orderedEvents.length) {
        const emptyNode = this.createGroupNode({
          id: `empty-${group.sessionId || idx}`,
          title: 'Waiting for tool execution',
          summary: 'No tool calls yet.',
          lane: 'agent',
          status: 'pending',
          timestamp: requestNode.timestamp,
          timeLabel: requestNode.timeLabel,
        });
        requestNode.children.push(emptyNode);
      }

      tree.push(requestNode);
    });

    return tree;
  }

  createGroupNode(config) {
    const node = {
      id: config.id || `group-${Math.random().toString(36).slice(2)}`,
      type: config.type || 'group',
      tool: '',
      category: config.category || '',
      categoryLabel: config.categoryLabel || '',
      status: config.status || 'complete',
      title: config.title || 'Group',
      summary: config.summary || '',
      timestamp: config.timestamp,
      timeLabel: config.timeLabel || '',
      lane: config.lane || 'phase',
      children: [],
      depth: 0,
      isGroup: true,
      originalEvent: {
        title: config.title || 'Group',
        summary: config.summary || '',
        category: config.category || '',
        categoryLabel: config.categoryLabel || '',
        status: config.status || 'complete',
        timeLabel: config.timeLabel || '',
        lane: config.lane || 'phase',
        timestamp: config.timestamp,
        sessionId: config.sessionId,
        inputData: config.inputData,
        description: config.description,
      },
    };

    this.eventMap.set(node.id, node.originalEvent);
    return node;
  }

  createNode(event) {
    const rawCategory = event.categoryKey || event.category || this.inferCategory(event);
    const categoryKey = rawCategory ? rawCategory.toString().toLowerCase() : '';
    const categoryLabel = event.categoryLabel || event.category || categoryKey;

    const node = {
      id: event.id || `evt-${Math.random().toString(36).slice(2)}`,
      type: event.type || this.inferType(event),
      tool: event.tool || '',
      category: categoryKey,
      categoryLabel,
      status: event.status || 'complete',
      title: event.title || event.tool || 'Event',
      summary: event.summary || '',
      timestamp: event.timestamp,
      timeLabel: event.timeLabel || '',
      lane: event.lane || 'agent',
      children: [],
      depth: 0,
      // Preserve original data for detail view
      originalEvent: event,
    };

    this.eventMap.set(node.id, event);
    return node;
  }

  inferType(event) {
    if (event.lane === 'user') return 'user_request';
    if (event.lane === 'memory') return 'memory_op';
    if (event.lane === 'tool') return 'tool_call';
    if (event.tool) return 'tool_call';
    return 'agent_response';
  }

  inferCategory(event) {
    if (event.category) return event.category.toString().toLowerCase();
    if (event.lane === 'user') return 'trigger';
    if (event.lane === 'memory') return 'memory';

    const tool = event.tool || '';
    const explorers = ['Read', 'Glob', 'Grep', 'Task', 'WebFetch', 'WebSearch', 'ListMcpResourcesTool'];
    const executors = ['Edit', 'Write', 'Bash', 'NotebookEdit'];
    const planners = ['TodoWrite', 'EnterPlanMode', 'ExitPlanMode', 'AskUserQuestion'];

    if (explorers.some(t => tool.includes(t))) return 'explore';
    if (executors.some(t => tool.includes(t))) return 'execute';
    if (planners.some(t => tool.includes(t))) return 'plan';
    if (tool.includes('Skill')) return 'skill';

    return 'respond';
  }

  resolveGroupSort(a, b) {
    const at = this.groupTimestamp(a);
    const bt = this.groupTimestamp(b);
    if (at !== bt) return at - bt;
    return (a.idx ?? 0) - (b.idx ?? 0);
  }

  groupTimestamp(group) {
    if (group?.req?.created_at) {
      const parsed = this.parseTimestamp(group.req.created_at);
      if (parsed !== null) return parsed;
    }
    const eventTimes = (group.events || [])
      .map((event) => event.timestamp)
      .filter((value) => value !== null && value !== undefined);
    if (eventTimes.length > 0) {
      return Math.min(...eventTimes);
    }
    return Infinity;
  }

  buildRequestNode(group, idx) {
    const request = group.req;
    const requestText = this.cleanRequestText(request?.text || '');
    const requestTitle = requestText ? `Request · ${requestText}` : 'Request · (no content)';
    const metaParts = [];
    const userLabel = request?.user_name || request?.user_id;
    const channelLabel = request?.channel_name || request?.channel_id;
    if (userLabel) metaParts.push(userLabel);
    if (channelLabel) metaParts.push(`#${channelLabel.replace('#', '')}`);
    if (request?.created_at) {
      const parsed = this.parseTimestamp(request.created_at);
      metaParts.push(parsed ? this.formatTime(parsed) : request.created_at);
    }

    const timestamp = request?.created_at ? this.parseTimestamp(request.created_at) : null;

    return this.createGroupNode({
      id: `req-${request?.request_id || group.sessionId || idx}`,
      title: requestTitle,
      summary: metaParts.join(' · '),
      lane: 'user',
      status: 'complete',
      timestamp,
      timeLabel: timestamp ? this.formatTime(timestamp) : '',
      sessionId: group.sessionId,
      inputData: request || {},
      description: requestText,
    });
  }

  buildThoughtText(event) {
    const raw = event.thought || event.summary || event.description || '';
    const cleaned = this.cleanInlineText(raw);
    if (cleaned) return this.truncate(cleaned, 90);

    const category = (event.categoryLabel || event.category || '').toString().toLowerCase();
    const toolLabel = event.toolLabel || event.title || event.tool || 'tool';
    const templates = {
      trigger: 'Understanding request',
      explore: 'Exploring information',
      plan: 'Organizing task plan',
      execute: 'Executing task',
      respond: 'Composing response',
      approval: 'Reviewing approval',
      memory: 'Checking memory',
    };

    const base = templates[category] || 'Processing task';
    return `${base} · ${toolLabel}`;
  }

  cleanRequestText(text) {
    if (!text) return '';
    let output = text;
    output = output.replace(/<@[A-Z0-9]+>/g, '');
    output = output.replace(/<#[A-Z0-9]+\|([^>]+)>/g, '#$1');
    output = output.replace(/<([^|>]+)\|([^>]+)>/g, '$2');
    output = output.replace(/<([^>]+)>/g, '$1');
    output = output.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
    output = output.replace(/\s+/g, ' ').trim();
    return this.truncate(output, 120);
  }

  cleanInlineText(text) {
    if (!text) return '';
    return text.replace(/\s+/g, ' ').trim();
  }

  parseTimestamp(value) {
    if (!value) return null;
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  formatTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  truncate(text, limit = 100) {
    if (!text) return '';
    if (text.length <= limit) return text;
    return `${text.slice(0, Math.max(0, limit - 1))}…`;
  }

  handleClick(event) {
    const node = event.target.closest('.tree-node');
    if (!node || !this.container.contains(node)) return;

    // Handle expand/collapse
    const toggle = event.target.closest('.tree-toggle');
    if (toggle) {
      const nodeId = node.dataset.eventId;
      if (this.collapsedNodes.has(nodeId)) {
        this.collapsedNodes.delete(nodeId);
      } else {
        this.collapsedNodes.add(nodeId);
      }
      this.render();
      return;
    }

    // Handle selection
    const eventId = node.dataset.eventId;
    if (!eventId) return;

    // Remove previous selection
    this.container.querySelectorAll('.tree-node.selected').forEach(el => {
      el.classList.remove('selected');
    });
    node.classList.add('selected');

    const payload = this.eventMap.get(eventId);
    if (payload && typeof this.onSelect === 'function') {
      this.onSelect(payload);
    }
  }

  render() {
    if (!this.container) return;

    if (!this.tree.length) {
      this.container.innerHTML = `<div class="empty-state">${this.options.emptyMessage}</div>`;
      return;
    }

    const html = this.tree.map(node => this.renderNode(node, 0, true)).join('');
    this.container.innerHTML = `<div class="tree-container">${html}</div>`;
  }

  renderNode(node, depth, isLast = false) {
    const hasChildren = node.children && node.children.length > 0;
    const isExpanded = !hasChildren || !this.collapsedNodes.has(node.id);

    const statusIcon = this.getStatusIcon(node.status);
    const categoryKey = node.category ? node.category.toString().toLowerCase() : '';
    const categoryClass = categoryKey ? `category-${categoryKey}` : '';
    const categoryLabel = node.categoryLabel || node.category || '';
    const showBadge = categoryLabel && !node.isGroup;

    // Build connector classes
    const connectorClasses = ['tree-line'];
    if (isLast) connectorClasses.push('last');
    if (hasChildren) connectorClasses.push('has-children');

    const html = `
      <div class="tree-node depth-${depth} ${isLast ? 'last' : ''}" data-event-id="${node.id}" style="--depth: ${depth}">
        <div class="tree-node-row">
          <div class="tree-indent">
            ${this.renderIndentGuides(depth)}
            <span class="${connectorClasses.join(' ')}"></span>
          </div>
          ${hasChildren ? `
            <button class="tree-toggle ${isExpanded ? 'expanded' : ''}" aria-label="Toggle">
              <svg viewBox="0 0 16 16" width="12" height="12">
                <path d="M6 4l4 4-4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          ` : '<span class="tree-toggle-placeholder"></span>'}
          <div class="tree-content ${node.lane} ${node.status}">
            <div class="tree-header">
              <span class="tree-time">${this.escapeHtml(node.timeLabel)}</span>
              <span class="tree-title">${this.escapeHtml(node.title)}</span>
              ${showBadge ? `<span class="tree-category ${categoryClass}">${this.escapeHtml(categoryLabel)}</span>` : ''}
              <span class="tree-status status-${node.status}">${statusIcon}</span>
            </div>
            ${node.summary && node.lane === 'user' ? `<div class="tree-summary">${this.escapeHtml(node.summary)}</div>` : ''}
            ${node.tool && node.lane !== 'tool' ? `<div class="tree-tool"><code>${this.escapeHtml(node.tool)}</code></div>` : ''}
          </div>
        </div>
        ${hasChildren && isExpanded ? `
          <div class="tree-children">
            ${node.children.map((child, i) => this.renderNode(child, depth + 1, i === node.children.length - 1)).join('')}
          </div>
        ` : ''}
      </div>
    `;

    return html;
  }

  renderIndentGuides(depth) {
    let guides = '';
    for (let i = 0; i < depth; i++) {
      guides += '<span class="tree-guide"></span>';
    }
    return guides;
  }

  getStatusIcon(status) {
    switch (status) {
      case 'complete': return '<span class="icon-complete">&#10003;</span>';
      case 'running': return '<span class="icon-running">&#10227;</span>';
      case 'error': return '<span class="icon-error">&#10007;</span>';
      case 'pending': return '<span class="icon-pending">&#9675;</span>';
      default: return '<span class="icon-default">&#8226;</span>';
    }
  }

  escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Auto-scroll to bottom for new events
  scrollToBottom() {
    if (this.container) {
      this.container.scrollTop = this.container.scrollHeight;
    }
  }

  // Expand all nodes
  expandAll() {
    this.collapsedNodes.clear();
    this.render();
  }

  // Collapse all nodes
  collapseAll() {
    const collectIds = (nodes) => {
      for (const node of nodes) {
        if (node.children && node.children.length > 0) {
          this.collapsedNodes.add(node.id);
          collectIds(node.children);
        }
      }
    };
    collectIds(this.tree);
    this.render();
  }
}

// For backward compatibility
class WorkflowFlow extends AgentTreeFlow {
  constructor(containerId, options) {
    super(containerId, options);
  }
}

window.AgentTreeFlow = AgentTreeFlow;
window.WorkflowFlow = WorkflowFlow;
