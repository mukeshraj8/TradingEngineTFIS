const OPERATOR_TABS = [
  { key: "system-monitor", label: "System Monitor", description: "Health, alerts, safety, and session state." },
  { key: "attention-queue", label: "Attention Queue", description: "Warnings, breaks, and operator review items." },
  { key: "opportunity-queue", label: "Opportunity Queue", description: "Which strategy instances are ready and why." },
  { key: "decision-workbench", label: "Decision Workbench", description: "Open one selected instance and inspect the decision path." },
  { key: "order-state", label: "Order State", description: "Current order queue and execution state." },
  { key: "open-positions", label: "Open Positions", description: "Open exposure, protection, and attention needs." },
  { key: "exposure-limits", label: "Exposure & Limits", description: "Exposure, limits, and capacity before action." },
  { key: "trade-history", label: "Trade History", description: "What happened previously and why." },
  { key: "audit-trail", label: "Audit Trail", description: "Immutable change and runtime history." },
  { key: "accounts-controls", label: "Accounts & Controls", description: "Account setup, authority boundaries, and controls." },
  { key: "platform-settings", label: "Platform Settings", description: "Projection metadata and local platform configuration." },
];

const OPERATOR_WORKFLOWS = [
  {
    key: "monitor",
    title: "Workflow 1 - Monitor the system",
    question: "Is everything healthy?",
    tabs: [
      { key: "system-monitor", label: "System Monitor", description: "Health, safety, and session state." },
      { key: "attention-queue", label: "Attention Queue", description: "Warnings and signals that need review." },
    ],
  },
  {
    key: "opportunities",
    title: "Workflow 2 - Review opportunities",
    question: "What strategies are ready to trade?",
    tabs: [
      { key: "opportunity-queue", label: "Opportunity Queue", description: "Strategy summaries and ready instrument instances." },
    ],
  },
  {
    key: "decision",
    title: "Workflow 3 - Validate one decision",
    question: "Why did the engine choose this contract?",
    tabs: [
      { key: "decision-workbench", label: "Decision Workbench", description: "Open one instance and validate the decision path." },
    ],
  },
  {
    key: "positions",
    title: "Workflow 4 - Manage positions",
    question: "What is currently open and does it need attention?",
    tabs: [
      { key: "open-positions", label: "Open Positions", description: "Protection, lifecycle, and P&L state." },
      { key: "order-state", label: "Order State", description: "Requested, filled, and waiting orders." },
      { key: "exposure-limits", label: "Exposure & Limits", description: "Capacity and warning checks before action." },
    ],
  },
  {
    key: "history",
    title: "Workflow 5 - Review history",
    question: "What happened yesterday and why?",
    tabs: [
      { key: "trade-history", label: "Trade History", description: "Past trades and their outcome." },
      { key: "audit-trail", label: "Audit Trail", description: "What changed and when." },
    ],
  },
  {
    key: "configure",
    title: "Workflow 6 - Configure the platform",
    question: "Accounts, limits, strategies, brokers, notifications.",
    tabs: [
      { key: "accounts-controls", label: "Accounts & Controls", description: "Accounts, permissions, and local controls." },
      { key: "platform-settings", label: "Platform Settings", description: "Snapshot metadata and local configuration." },
    ],
  },
];

const OPERATOR_ROUTE_TO_WORKSPACE = {
  "system-monitor": "command-centre",
  "attention-queue": "alerts",
  "opportunity-queue": "strategies",
  "decision-workbench": "strategies",
  "order-state": "orders",
  "open-positions": "positions",
  "exposure-limits": "risk",
  "trade-history": "historical-trades",
  "audit-trail": "audit",
  "accounts-controls": "accounts",
  "platform-settings": "settings",
};

const MODE_ROUTE_FALLBACKS = {
  operator: "system-monitor",
  engineering: "decision-explorer",
};

const OPERATOR_TO_ENGINEERING_ROUTE = {
  "system-monitor": "diagnostics",
  "attention-queue": "diagnostics",
  "opportunity-queue": "decision-explorer",
  "decision-workbench": "decision-explorer",
  "order-state": "decision-explorer",
  "open-positions": "decision-explorer",
  "exposure-limits": "diagnostics",
  "trade-history": "replay",
  "audit-trail": "source-trace",
  "accounts-controls": "manual-validation",
  "platform-settings": "diagnostics",
};

const ENGINEERING_TO_OPERATOR_ROUTE = {
  "decision-explorer": "decision-workbench",
  "monthly-status-review": "decision-workbench",
  "contract-selection-audit": "decision-workbench",
  "manual-validation": "decision-workbench",
  "replay": "trade-history",
  "explanation-library": "decision-workbench",
  "diagnostics": "system-monitor",
  "source-trace": "decision-workbench",
};

const ENGINEERING_TABS = [
  { key: "decision-explorer", label: "Decision Explorer", description: "Stepwise engineering review of one selected strategy instance." },
  { key: "monthly-status-review", label: "Monthly Status", description: "Dedicated review of Monthly Status output and evidence limits." },
  { key: "contract-selection-audit", label: "Contract Selection", description: "Candidate audit, selected contract, and rejection reasons." },
  { key: "manual-validation", label: "Manual Validation", description: "Local-only engine versus manual comparison workspace." },
  { key: "replay", label: "Replay", description: "Historical reconstruction and replay availability." },
  { key: "explanation-library", label: "Explanation Library", description: "All immutable decision facts across strategies." },
  { key: "diagnostics", label: "Diagnostics", description: "Runtime diagnostics and raw technical details." },
  { key: "source-trace", label: "Source Trace", description: "Workbook, rule, and evidence-source trace for the selected strategy." },
];

const EXPLAIN_TABS = [
  { key: "overview", label: "Overview" },
  { key: "monthly-status", label: "Monthly Status" },
  { key: "branch", label: "Branch" },
  { key: "market-structure", label: "Market Structure" },
  { key: "contract-selection", label: "Contract Selection" },
  { key: "entry", label: "Entry Calculation" },
  { key: "orpt-rc", label: "ORPT / RC" },
  { key: "protection", label: "Target / SL" },
  { key: "order-position", label: "Order & Position" },
  { key: "pnl", label: "P&L" },
  { key: "timeline", label: "Timeline" },
  { key: "manual", label: "Manual Comparison" },
  { key: "source-trace", label: "Source Trace" },
];

const GUIDE_STEPS = [
  ["Workflow 1 - Monitor the system", "Start with health, alerts, and safety boundaries before trusting any trade state."],
  ["Workflow 2 - Review opportunities", "Use the strategy summary and compact instance list to find which instruments are prepared or ready."],
  ["Workflow 3 - Validate one decision", "Open one instance and inspect Monthly Status, branch, contract selection, entry timing, and protection step by step."],
  ["Workflow 4 - Manage positions", "Check open positions, protection state, order state, and risk together before taking any action."],
  ["Workflow 5 - Review history", "Use historical trades and audit history to understand what happened in previous sessions and why."],
  ["Workflow 6 - Configure the platform", "Review accounts, limits, local settings, and authority boundaries without confusing them with live execution."],
];

const REQUIRED_STAGE_KEYS = [
  "monthly-status",
  "branch",
  "market-structure",
  "contract-selection",
  "entry",
  "orpt-rc",
  "protection",
  "order-position",
  "pnl",
  "timeline",
  "source-trace",
];

const VALUE_LABELS = {
  BULL: "Bullish",
  BULL_CF: "Bullish confirmed",
  BEAR: "Bearish",
  BEAR_CF: "Bearish confirmed",
  BULL_CALL: "Bullish call branch",
  BEAR_CALL: "Bearish call branch",
  BULL_PUT: "Bullish put branch",
  BEAR_PUT: "Bearish put branch",
  READ_ONLY_OR_INTERNAL: "Read-only market data / internal paper execution",
  READ_ONLY_OR_INTERNAL_PAPER: "Read-only market data / internal paper execution",
  INTERNAL_PAPER_CONTROLLED: "Controlled internal paper mode",
  INTERNAL_PAPER: "Internal paper",
  INTERNAL_PAPER_LOCAL_ONLY: "Local internal paper only",
  READ_ONLY_OPERATOR_PLATFORM: "Read-only operator platform",
  PROCESSED_INTERNAL_PAPER: "Processed in internal paper",
  FILLED_INTERNAL: "Filled in internal paper",
  NO_ORDER: "No order created",
  OPEN_PROTECTED: "Open position protected",
  OPEN_UNPROTECTED: "Open position missing protection",
  NO_POSITION: "No open position",
  PROTECTED: "Protection active",
  MISSING_PROTECTION: "Protection missing",
  HEALTHY: "Healthy",
  DEGRADED: "Needs review",
  DEGRADED_EVIDENCE: "Evidence limited - review carefully",
  DETERMINISTIC_SESSION: "Deterministic review session",
  DETERMINISTIC_TIMING_SUPPLEMENT: "Timing came from deterministic supplement",
  FIXTURE_BACKED: "Derived from fixture-backed evidence",
  HISTORICAL_RECONSTRUCTION: "Reconstructed from historical market evidence",
  ACTIVE: "Active",
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
  WARNING: "Warning",
  CRITICAL: "Critical",
  FRESH: "Fresh today",
  CARRIED: "Carried from previous session",
  AVAILABLE: "Available",
  NONE: "None",
  CONFIGURED_READ_ONLY_OR_INTERNAL: "Configured for read-only data and internal paper execution",
  PROVISIONAL_INTERNAL_PAPER: "Provisional internal paper estimate",
  INTERNAL_PAPER_DERIVED_FROM_SIMULATED_FILLS: "Derived from simulated internal-paper fills",
};

const KEY_LABELS = {
  active_orders: "Active orders",
  blocked_instances: "Blocked instances",
  broker_sessions: "Broker session mode",
  broker_data_session: "Broker data session",
  critical_alerts: "Critical alerts",
  enabled_strategy_instances: "Enabled strategy instances",
  enabled_instruments: "Enabled instruments",
  margin_usage_pct: "Margin usage %",
  market_state: "Market state",
  open_positions: "Open positions",
  plans_prepared: "Plans prepared",
  realized_pnl: "Realized P&L",
  system_state: "System state",
  unprotected_positions: "Unprotected positions",
  unrealized_pnl: "Unrealized P&L",
  last_market_update: "Last market update",
  read_only_or_order_authorised: "Data access / order authority",
  data_only_or_trading: "Data mode / trading mode",
  starting_capital: "Starting capital",
  simulated_balance: "Simulated balance",
  daily_loss_limit: "Daily loss limit",
  maximum_account_margin_usage_pct: "Maximum allowed margin usage %",
  maximum_new_entries_per_session: "Maximum new entries per session",
  maximum_concurrent_positions: "Maximum concurrent positions",
  save_mode: "Save mode",
  authority_mode: "Authority mode",
  projection_mode: "Projection mode",
  accounting_quality: "Accounting quality",
  charges_quality: "Charges quality",
  evidence_quality: "Evidence quality",
  current_action: "Current action",
  runtime_stage: "Runtime stage",
  entry_eligibility: "Entry eligibility",
};

const state = {
  projection: null,
  mode: "operator",
  activeTab: "system-monitor",
  selectedStrategyId: null,
  selectedDefinitionId: null,
  explainTab: "overview",
  selectionWarning: null,
  routeSyncInProgress: false,
  manualInputs: {},
  sort: {},
  strategyView: {
    quickView: "all",
    search: "",
    filters: {
      status: "all",
      monthly: "all",
      branch: "all",
      health: "all",
      evidence: "all",
      account: "all",
      enabled: "all",
    },
    sortKey: "last_update",
    sortDir: "desc",
    page: 1,
    pageSize: 10,
    density: "compact",
  },
};

const columns = {
  strategyDefinitionsTable: ["Strategy", "Family", "Segment", "Supported", "Enabled", "Prepared", "Qualified", "Entry Available", "Open", "Carried", "Blocked", "No Trade", "Realized P&L", "Unrealized P&L", "Margin Usage", "Health", "Evidence", "Last Update"],
  strategyInstancesTable: ["Instrument", "Enabled", "Account", "Monthly Status", "Branch", "Current Stage", "Selected Contract", "Entry", "Position", "Realized P&L", "Unrealized P&L", "Health", "Evidence", "Last Update", "Action"],
  ordersTable: ["Account", "Order", "Strategy", "Instrument", "Contract", "Side", "Qty", "Entry", "Target", "Stop-Loss", "Opened", "State", "Latest Event", "Notes"],
  positionsTable: ["Account", "Position", "Strategy", "Instrument", "Contract", "Side", "Qty", "Entry Time", "Avg Entry", "Mark", "Target", "Active SL", "P&L", "Exit Deadline", "Health"],
  explainabilityTable: ["Strategy", "Instrument", "Stage", "Rule", "Workbook", "Formula", "Inputs", "Intermediates", "Output", "Rejected Candidates", "Evidence", "Result"],
  engineeringExplainabilityTable: ["Strategy", "Instrument", "Stage", "Rule", "Workbook", "Formula", "Inputs", "Intermediates", "Output", "Rejected Candidates", "Evidence", "Result"],
  historicalTradesTable: ["Strategy", "Account", "Instrument", "Contract", "Entry Time", "Exit Time", "Side", "Quantity", "Entry Price", "Exit Price", "Exit Reason", "Gross P&L", "Net P&L", "Evidence Quality", "Explanation Completeness"],
  auditTable: ["Operator", "Timestamp", "Command", "Scope", "Reason", "Preview", "Result", "Previous", "New", "Evidence Hash"],
};

function init() {
  document.getElementById("themeToggle").addEventListener("click", toggleTheme);
  document.getElementById("modeOperator").addEventListener("click", () => switchMode("operator"));
  document.getElementById("modeEngineering").addEventListener("click", () => switchMode("engineering"));
  document.getElementById("strategyFilter").addEventListener("input", renderWorkbench);
  document.getElementById("strategyRailSearch").addEventListener("input", renderStrategyRail);
  document.getElementById("strategyStatusFilter").addEventListener("change", onStrategyFilterChange);
  document.getElementById("strategyMonthlyFilter").addEventListener("change", onStrategyFilterChange);
  document.getElementById("strategyBranchFilter").addEventListener("change", onStrategyFilterChange);
  document.getElementById("strategyHealthFilter").addEventListener("change", onStrategyFilterChange);
  document.getElementById("strategyEvidenceFilter").addEventListener("change", onStrategyFilterChange);
  document.getElementById("strategyAccountFilter").addEventListener("change", onStrategyFilterChange);
  document.getElementById("strategyEnabledFilter").addEventListener("change", onStrategyFilterChange);
  document.getElementById("strategySortKey").addEventListener("change", onStrategySortChange);
  document.getElementById("strategySortDirection").addEventListener("click", toggleStrategySortDirection);
  document.getElementById("strategyPageSize").addEventListener("change", onStrategyPageSizeChange);
  document.getElementById("strategyDensityToggle").addEventListener("click", toggleStrategyDensity);
  document.getElementById("strategySaveView").addEventListener("click", saveStrategyView);
  document.getElementById("strategySavedViews").addEventListener("change", applySavedStrategyView);
  document.getElementById("strategyExport").addEventListener("click", exportStrategyView);
  document.getElementById("strategyBackToList").addEventListener("click", () => {
    state.activeTab = "opportunity-queue";
    syncRouteState();
    render();
  });
  document.getElementById("strategyPrevInstance").addEventListener("click", () => selectAdjacentStrategy(-1));
  document.getElementById("strategyNextInstance").addEventListener("click", () => selectAdjacentStrategy(1));
  document.getElementById("explainabilityFilter").addEventListener("input", renderExplainabilityLibrary);
  document.getElementById("engineeringExplainabilityFilter").addEventListener("input", renderEngineeringExplainabilityLibrary);
  window.addEventListener("hashchange", applyHashRoute);
  applyHashRoute();
  renderPrimaryTabs();
  renderWorkflowGuide();
  loadProjection().catch(error => {
    document.body.innerHTML = `<main class="workspace-tab error-state"><h1>Dashboard unavailable</h1><pre>${escapeHtml(error.message)}</pre></main>`;
  });
  setInterval(() => {
    loadProjection().catch(() => {});
  }, 5000);
}

async function loadProjection() {
  const response = await fetch("api/snapshot.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Snapshot request failed: ${response.status}`);
  }
  state.projection = normalizeProjection(await response.json());
  ensureSelectedStrategy();
  render();
}

function ensureSelectedStrategy() {
  const strategies = state.projection?.strategies || [];
  const definitions = state.projection?.strategy_definitions || [];
  state.selectionWarning = null;
  if (definitions.length && !definitions.some(item => item.strategy_definition_id === state.selectedDefinitionId)) {
    state.selectedDefinitionId = definitions[0].strategy_definition_id;
  }
  if (!strategies.length) {
    state.selectedStrategyId = null;
    return;
  }
  if (state.selectedStrategyId && !strategies.some(item => item.identity.instance === state.selectedStrategyId)) {
    state.selectedStrategyId = null;
    state.selectionWarning = "SELECTED_INSTANCE_NO_LONGER_AVAILABLE";
  }
  if (state.selectedStrategyId) {
    const selected = strategies.find(item => item.identity.instance === state.selectedStrategyId);
    if (selected?.identity?.strategy_definition_id) {
      state.selectedDefinitionId = selected.identity.strategy_definition_id;
    }
  }
  if (!state.selectedDefinitionId && strategies.length) {
    state.selectedDefinitionId = strategies[0].identity.strategy_definition_id;
  }
  populateStrategyFilterControls();
}

function render() {
  const projection = state.projection;
  if (!projection) {
    return;
  }
  document.getElementById("authorityBadge").textContent = `Broker order authority: ${projection.system?.broker_order_authority || "UNKNOWN"}`;
  document.getElementById("sessionBadge").textContent = projection.system?.session || "Session unavailable";
  document.getElementById("headerSummary").textContent = buildHeaderSummary(projection);
  renderPrimaryTabs();
  renderProjectionWarnings();
  renderStrategyRouteState();
  renderOverview();
  renderStrategyRail();
  renderWorkbench();
  renderExplorer();
  renderOrders();
  renderPositions();
  renderAccounts();
  renderRisk();
  renderDecisionExplorerWorkspace();
  renderMonthlyStatusReview();
  renderContractSelectionAudit();
  renderManualValidationWorkspace();
  renderReplayWorkspace();
  renderExplainabilityLibrary();
  renderEngineeringExplainabilityLibrary();
  renderHistoricalTrades();
  renderAlerts();
  renderAudit();
  renderDiagnostics();
  renderSourceTraceWorkspace();
  renderSettings();
  updateVisibleWorkspace();
}

function buildHeaderSummary(projection) {
  const centre = projection.command_centre || {};
  return `Workflow-ready snapshot: ${display(centre.enabled_strategy_instances)} active strategy instances, ${display(centre.open_positions)} open positions, and session mode ${display(centre.market_state)}.`;
}

function renderProjectionWarnings() {
  const target = document.getElementById("projectionWarnings");
  const warnings = state.projection?.projection_reconciliation?.warnings || [];
  const status = state.projection?.projection_reconciliation?.status;
  if (!warnings.length && status !== "DEGRADED_PROJECTION") {
    target.innerHTML = "";
    target.style.display = "none";
    return;
  }
  target.style.display = "";
  target.innerHTML = [
    status === "DEGRADED_PROJECTION" ? renderWarningBox("Projection inconsistency detected. This view is being shown with degraded projection truth. Review the missing fields below before trusting counts.") : "",
    ...warnings.map(item => renderWarningBox(item)),
  ].join("");
}

function renderStrategyRouteState() {
  const workspaceRoute = getWorkspaceRoute();
  const routeKicker = document.getElementById("strategyRouteKicker");
  const routeTitle = document.getElementById("strategyRouteTitle");
  const opportunityPanels = document.getElementById("opportunityQueuePanels");
  const decisionPanels = document.getElementById("decisionWorkbenchPanels");
  const breadcrumb = document.getElementById("strategyBreadcrumb");
  const selected = getSelectedStrategy();
  const selectedDefinition = getSelectedDefinition();

  if (workspaceRoute === "decision-workbench") {
    routeKicker.textContent = "Workflow 3 - Validate one decision";
    routeTitle.textContent = "Why did the engine choose this contract?";
    opportunityPanels.style.display = "none";
    decisionPanels.style.display = "";
  } else {
    routeKicker.textContent = "Workflow 2 - Review opportunities";
    routeTitle.textContent = "What is ready to trade?";
    opportunityPanels.style.display = "";
    decisionPanels.style.display = "none";
  }

  const crumb = ["Operator"];
  if (workspaceRoute === "decision-workbench") {
    crumb.push("Validate One Decision");
  } else {
    crumb.push("Review Opportunities");
  }
  if (selectedDefinition?.strategy_code) {
    crumb.push(selectedDefinition.strategy_code);
  }
  if (selected?.identity?.instrument) {
    crumb.push(selected.identity.instrument);
  }
  if (workspaceRoute === "decision-workbench") {
    crumb.push(explainTabLabel(state.explainTab));
  }
  breadcrumb.textContent = crumb.join(" > ");
}

function renderPrimaryTabs() {
  const container = document.getElementById("primaryTabs");
  const tabs = state.mode === "operator" ? OPERATOR_TABS : ENGINEERING_TABS;
  if (state.mode === "operator") {
    container.innerHTML = OPERATOR_WORKFLOWS.map(workflow => `
      <div class="workflow-group">
        <div class="workflow-heading">
          <strong>${escapeHtml(workflow.title)}</strong>
          <span>${escapeHtml(workflow.question)}</span>
        </div>
        <div class="workflow-tabs">
          ${workflow.tabs.map(workflowTab => {
            const tab = tabs.find(item => item.key === workflowTab.key);
            if (!tab) return "";
            return `
              <button type="button" class="nav-button ${state.activeTab === workflowTab.key ? "is-active" : ""}" data-tab="${workflowTab.key}">
                <span class="nav-label">${escapeHtml(workflowTab.label || tab.label)}</span>
                <span class="nav-copy">${escapeHtml(workflowTab.description || tab.description)}</span>
              </button>
            `;
          }).join("")}
        </div>
      </div>
    `).join("");
  } else {
    container.innerHTML = tabs.map(tab => `
      <button type="button" class="nav-button ${state.activeTab === tab.key ? "is-active" : ""}" data-tab="${tab.key}">
        <span class="nav-label">${escapeHtml(tab.label)}</span>
        <span class="nav-copy">${escapeHtml(tab.description)}</span>
      </button>
    `).join("");
  }
  container.querySelectorAll(".nav-button").forEach(button => {
    button.addEventListener("click", () => {
      const nextTab = button.dataset.tab;
      if (state.activeTab === nextTab) {
        focusActiveWorkspace();
        return;
      }
      state.activeTab = nextTab;
      syncRouteState();
      render();
    });
  });
}

function switchMode(mode) {
  state.mode = mode;
  const tabs = mode === "operator" ? OPERATOR_TABS : ENGINEERING_TABS;
  if (!tabs.some(item => item.key === state.activeTab)) {
    state.activeTab = mode === "operator"
      ? (ENGINEERING_TO_OPERATOR_ROUTE[state.activeTab] || MODE_ROUTE_FALLBACKS.operator)
      : (OPERATOR_TO_ENGINEERING_ROUTE[state.activeTab] || MODE_ROUTE_FALLBACKS.engineering);
  }
  document.getElementById("modeOperator").classList.toggle("is-active", mode === "operator");
  document.getElementById("modeEngineering").classList.toggle("is-active", mode === "engineering");
  syncRouteState();
  render();
}

function renderWorkflowGuide() {
  const target = document.getElementById("workflowGuide");
  target.innerHTML = GUIDE_STEPS.map(([title, copy]) => `
    <div class="guide-item">
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(copy)}</p>
    </div>
  `).join("");
}

function getWorkspaceRoute() {
  if (state.mode === "operator") {
    return state.activeTab;
  }
  return ENGINEERING_TO_OPERATOR_ROUTE[state.activeTab] || "decision-workbench";
}

function explainTabLabel(key) {
  return (EXPLAIN_TABS.find(item => item.key === key) || EXPLAIN_TABS[0]).label;
}

function focusActiveWorkspace() {
  const workspace = document.getElementById(`tab-${resolveWorkspaceTabKey(state.activeTab)}`);
  if (!workspace) return;
  const heading = workspace.querySelector("h2, h3");
  if (heading && typeof heading.scrollIntoView === "function") {
    heading.scrollIntoView({ behavior: "smooth", block: "start" });
  } else if (typeof workspace.scrollIntoView === "function") {
    workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function resolveWorkspaceTabKey(activeTab) {
  if (state.mode === "operator") {
    return OPERATOR_ROUTE_TO_WORKSPACE[activeTab] || "command-centre";
  }
  return activeTab;
}

function syncRouteState() {
  if (state.routeSyncInProgress) {
    return;
  }
  const params = new URLSearchParams();
  params.set("mode", state.mode);
  if (state.selectedDefinitionId) params.set("definition", state.selectedDefinitionId);
  if (state.selectedStrategyId) params.set("instance", state.selectedStrategyId);
  if (state.explainTab) params.set("step", state.explainTab);
  const hash = `${state.activeTab}${params.toString() ? `?${params.toString()}` : ""}`;
  state.routeSyncInProgress = true;
  window.location.hash = hash;
  state.routeSyncInProgress = false;
}

function applyHashRoute() {
  if (state.routeSyncInProgress) {
    return;
  }
  const raw = String(window.location.hash || "").replace(/^#/, "");
  if (!raw) {
    return;
  }
  const [routePart, queryPart = ""] = raw.split("?");
  const params = new URLSearchParams(queryPart);
  const mode = params.get("mode");
  if (mode === "operator" || mode === "engineering") {
    state.mode = mode;
  }
  const availableTabs = state.mode === "operator" ? OPERATOR_TABS : ENGINEERING_TABS;
  if (availableTabs.some(item => item.key === routePart)) {
    state.activeTab = routePart;
  }
  state.selectedDefinitionId = params.get("definition") || state.selectedDefinitionId;
  state.selectedStrategyId = params.get("instance") || state.selectedStrategyId;
  state.explainTab = params.get("step") || state.explainTab;
  document.getElementById("modeOperator").classList.toggle("is-active", state.mode === "operator");
  document.getElementById("modeEngineering").classList.toggle("is-active", state.mode === "engineering");
}

function normalizeProjection(rawProjection) {
  const projection = { ...(rawProjection || {}) };
  const warnings = [];
  const strategies = Array.isArray(projection.strategies) ? projection.strategies : [];

  if ((!Array.isArray(projection.strategy_instances) || !projection.strategy_instances.length) && strategies.length) {
    warnings.push("Missing snapshot field: strategy_instances. Derived operator rows from strategy read models.");
    projection.strategy_instances = deriveStrategyInstances(strategies);
  } else {
    projection.strategy_instances = Array.isArray(projection.strategy_instances) ? projection.strategy_instances : [];
  }

  if ((!Array.isArray(projection.strategy_definitions) || !projection.strategy_definitions.length) && projection.strategy_instances.length) {
    warnings.push("Missing snapshot field: strategy_definitions. Derived definition summaries from strategy instance rows.");
    projection.strategy_definitions = deriveStrategyDefinitions(projection.strategy_instances);
  } else {
    projection.strategy_definitions = Array.isArray(projection.strategy_definitions) ? projection.strategy_definitions : [];
  }

  if ((!projection.strategy_status_counts || !projection.strategy_status_counts.global) && projection.strategy_instances.length) {
    warnings.push("Missing snapshot field: strategy_status_counts. Derived grouped counts from strategy instance rows.");
    projection.strategy_status_counts = deriveStrategyStatusCounts(projection.strategy_instances);
  }

  if ((!projection.strategy_filter_options || !Object.keys(projection.strategy_filter_options).length) && projection.strategy_instances.length) {
    warnings.push("Missing snapshot field: strategy_filter_options. Derived queue filter options from strategy instance rows.");
    projection.strategy_filter_options = deriveStrategyFilterOptions(projection.strategy_instances, projection.strategy_definitions);
  }

  if ((!projection.navigation || !Array.isArray(projection.navigation.strategy_groups) || !projection.navigation.strategy_groups.length) && projection.strategy_definitions.length) {
    warnings.push("Missing snapshot field: navigation.strategy_groups. Derived strategy navigation groups from definition summaries.");
    projection.navigation = {
      ...(projection.navigation || {}),
      strategy_groups: deriveStrategyGroups(projection.strategy_definitions, projection.strategy_status_counts),
    };
  }

  if ((!Array.isArray(projection.strategy_families) || !projection.strategy_families.length) && projection.strategy_instances.length) {
    warnings.push("Missing snapshot field: strategy_families. Derived family summary from strategy instance rows.");
    projection.strategy_families = deriveStrategyFamilies(projection.strategy_instances);
  }

  const reconciliation = reconcileProjection(projection);
  projection.projection_reconciliation = {
    status: warnings.length || reconciliation.warnings.length ? "DEGRADED_PROJECTION" : "HEALTHY",
    warnings: [...warnings, ...reconciliation.warnings],
    counts: reconciliation.counts,
  };
  return projection;
}

function deriveStrategyInstances(strategies) {
  return strategies.map(item => ({
    strategy_instance_id: item.identity?.strategy_instance_id || item.identity?.instance,
    strategy_definition_id: item.identity?.strategy_definition_id || item.identity?.strategy,
    strategy_code: item.identity?.strategy,
    strategy_display_name: item.identity?.strategy_display_name || item.identity?.strategy,
    family: item.identity?.product_label || item.identity?.product,
    segment: item.identity?.segment_label || item.identity?.segment,
    instrument: item.identity?.instrument,
    enabled: item.state?.enabled ?? true,
    enabled_label: item.state?.enabled_label || ((item.state?.enabled ?? true) ? "Enabled" : "Disabled"),
    account: item.identity?.account,
    account_display_name: item.identity?.account_display_name || item.identity?.account,
    monthly_status: item.state?.monthly_status,
    branch: item.state?.branch,
    current_stage: item.state?.runtime_stage,
    selected_contract: item.plan?.selected_contract,
    entry: item.plan?.base_entry,
    position: item.position?.health,
    position_label: item.position?.health_label || item.position?.health,
    fresh_or_carried: item.position?.fresh_or_carried,
    realized_pnl: item.accounting?.realized_pnl,
    unrealized_pnl: item.accounting?.unrealized_pnl,
    health: item.state?.health,
    health_label: item.state?.health_label || item.state?.health,
    evidence: item.state?.evidence_quality,
    evidence_label: item.state?.evidence_quality_label || item.state?.evidence_quality,
    last_update: item.state?.last_update,
    alerts: item.operations?.alerts || [],
    has_alerts: Boolean(item.operations?.alerts?.length),
    entry_available: ["NORMAL_ENTRY_STILL_VALID", "RC_ENTRY_STILL_VALID", "ENTRY_AVAILABLE"].includes(String(item.state?.runtime_stage || "").toUpperCase()),
    blocked: String(item.state?.runtime_stage || "").toUpperCase().startsWith("BLOCKED"),
    no_trade: String(item.execution?.order_state || "").toUpperCase() === "NO_ORDER" && !String(item.position?.health || "").toUpperCase().startsWith("OPEN"),
    qualified: Boolean(item.plan?.selected_contract),
  }));
}

function deriveStrategyDefinitions(rows) {
  const grouped = new Map();
  rows.forEach(row => {
    const key = row.strategy_definition_id;
    const bucket = grouped.get(key) || [];
    bucket.push(row);
    grouped.set(key, bucket);
  });
  return Array.from(grouped.entries()).map(([definitionId, bucket]) => {
    const first = bucket[0] || {};
    return {
      strategy_definition_id: definitionId,
      strategy_code: first.strategy_code,
      display_name: first.strategy_display_name || first.strategy_code,
      family: first.family,
      segment: first.segment,
      supported_count: bucket.length,
      enabled_count: bucket.filter(item => item.enabled).length,
      prepared_count: bucket.filter(item => item.current_stage).length,
      qualified_count: bucket.filter(item => item.qualified).length,
      entry_available_count: bucket.filter(item => item.entry_available).length,
      open_count: bucket.filter(item => String(item.position || "").startsWith("OPEN")).length,
      carried_count: bucket.filter(item => item.fresh_or_carried === "CARRIED").length,
      blocked_count: bucket.filter(item => item.blocked).length,
      no_trade_count: bucket.filter(item => item.no_trade).length,
      realized_pnl: sumPnl(bucket, "realized_pnl"),
      unrealized_pnl: sumPnl(bucket, "unrealized_pnl"),
      margin_usage_pct: bucket.filter(item => String(item.position || "").startsWith("OPEN")).length * 18,
      health: aggregateText(bucket.map(item => item.health), "HEALTHY"),
      evidence_quality: aggregateText(bucket.map(item => item.evidence_label || item.evidence), "UNKNOWN"),
      last_update: aggregateText(bucket.map(item => item.last_update), ""),
    };
  });
}

function deriveStrategyStatusCounts(rows) {
  const countsFor = items => ({
    all: items.length,
    enabled: items.filter(item => item.enabled).length,
    entry_available: items.filter(item => item.entry_available).length,
    open_positions: items.filter(item => String(item.position || "").startsWith("OPEN")).length,
    carried: items.filter(item => item.fresh_or_carried === "CARRIED").length,
    blocked: items.filter(item => item.blocked).length,
    no_trade: items.filter(item => item.no_trade).length,
    missing_evidence: items.filter(item => ["DEGRADED_EVIDENCE", "DETERMINISTIC_TIMING_SUPPLEMENT"].includes(String(item.evidence || "").toUpperCase())).length,
    alerts: items.filter(item => item.has_alerts).length,
  });
  const grouped = {};
  rows.forEach(item => {
    grouped[item.strategy_definition_id] = grouped[item.strategy_definition_id] || [];
    grouped[item.strategy_definition_id].push(item);
  });
  return {
    global: countsFor(rows),
    by_definition: Object.fromEntries(Object.entries(grouped).map(([key, items]) => [key, countsFor(items)])),
  };
}

function deriveStrategyFilterOptions(rows, definitions) {
  return {
    definitions: (definitions || []).map(item => ({
      strategy_definition_id: item.strategy_definition_id,
      strategy_code: item.strategy_code,
      display_name: item.display_name,
    })),
    accounts: uniqueSorted(rows.map(item => item.account_display_name || item.account)),
    monthly_statuses: uniqueSorted(rows.map(item => item.monthly_status)),
    branches: uniqueSorted(rows.map(item => item.branch)),
    stages: uniqueSorted(rows.map(item => item.current_stage)),
    health: uniqueSorted(rows.map(item => item.health)),
    evidence: uniqueSorted(rows.map(item => item.evidence)),
    sort_fields: [
      { key: "realized_pnl", label: "Realized P&L" },
      { key: "unrealized_pnl", label: "Unrealized P&L" },
      { key: "current_stage", label: "Current Stage" },
      { key: "last_update", label: "Last Update" },
      { key: "instrument", label: "Instrument" },
    ],
    page_sizes: [10, 20, 50],
  };
}

function deriveStrategyGroups(definitions, statusCounts) {
  const grouped = new Map();
  (definitions || []).forEach(item => {
    const family = item.family || "Unclassified";
    const bucket = grouped.get(family) || [];
    bucket.push({
      strategy_definition_id: item.strategy_definition_id,
      strategy_code: item.strategy_code,
      display_name: item.display_name,
      enabled_count: item.enabled_count,
      supported_count: item.supported_count,
      status_counts: statusCounts?.by_definition?.[item.strategy_definition_id] || {},
    });
    grouped.set(family, bucket);
  });
  return Array.from(grouped.entries()).map(([family, definitionsInFamily]) => ({
    family,
    definitions: definitionsInFamily,
  }));
}

function deriveStrategyFamilies(rows) {
  const grouped = new Map();
  rows.forEach(row => {
    const family = row.family || "Unclassified";
    const bucket = grouped.get(family) || [];
    bucket.push(row);
    grouped.set(family, bucket);
  });
  return Array.from(grouped.entries()).map(([family, bucket]) => ({
    family,
    instrument_count: bucket.length,
    strategy_count: uniqueSorted(bucket.map(item => item.strategy_code)).length,
    active_positions: bucket.filter(item => String(item.position || "").startsWith("OPEN")).length,
    blocked: bucket.filter(item => item.blocked).length,
    no_trade: bucket.filter(item => item.no_trade).length,
    daily_pnl: String(Number(sumPnl(bucket, "realized_pnl")) + Number(sumPnl(bucket, "unrealized_pnl"))),
    evidence_quality: aggregateText(bucket.map(item => item.evidence_label || item.evidence), "UNKNOWN"),
    health: aggregateText(bucket.map(item => item.health), "HEALTHY"),
    scalability_demo: false,
  }));
}

function reconcileProjection(projection) {
  const warnings = [];
  const definitions = projection.strategy_definitions || [];
  const instances = projection.strategy_instances || [];
  const strategies = projection.strategies || [];
  const positions = projection.positions || [];
  const counts = {
    command_centre_enabled_strategy_instances: projection.command_centre?.enabled_strategy_instances ?? null,
    projected_strategy_instances: instances.length,
    projected_strategy_definitions: definitions.length,
    projected_read_models: strategies.length,
    projected_open_positions: positions.filter(item => String(item.health || "").startsWith("OPEN")).length,
  };
  if (counts.command_centre_enabled_strategy_instances !== null && counts.command_centre_enabled_strategy_instances !== counts.projected_read_models) {
    warnings.push(`Header count mismatch: command_centre.enabled_strategy_instances=${counts.command_centre_enabled_strategy_instances}, strategies=${counts.projected_read_models}.`);
  }
  if (instances.length && strategies.length && instances.length !== strategies.length) {
    warnings.push(`Projection mismatch: strategy_instances=${instances.length}, strategies=${strategies.length}.`);
  }
  positions.forEach(position => {
    const instrument = position.instrument;
    const known = strategies.some(item => item.identity?.instrument === instrument);
    if (!known) {
      warnings.push(`Open position for ${instrument} does not reference a known StrategyInstance.`);
    }
  });
  return { warnings, counts };
}

function uniqueSorted(values) {
  return Array.from(new Set((values || []).filter(item => item !== null && item !== undefined && item !== ""))).sort((a, b) => String(a).localeCompare(String(b), undefined, { numeric: true }));
}

function sumPnl(rows, key) {
  return rows.reduce((total, item) => total + (Number(item[key] || 0) || 0), 0).toFixed(2);
}

function aggregateText(values, fallback) {
  const cleaned = uniqueSorted(values);
  return cleaned.length ? cleaned.join(", ") : fallback;
}

function renderOverview() {
  const projection = state.projection;
  renderMetricCards("statusGrid", projection.command_centre || {});
  const narrative = document.getElementById("overviewNarrative");
  const selected = getSelectedStrategy();
  const alerts = projection.alerts || [];
  const facts = projection.decision_explanations || [];
  const definitions = projection.strategy_definitions || [];
  const scopeSummary = definitions.length === 1
    ? `${display(definitions[0].display_name || definitions[0].strategy_code)} only in this snapshot.`
    : `${definitions.length} strategy definitions are included in this snapshot.`;
  narrative.innerHTML = [
    summaryRow("Snapshot", scopeSummary),
    summaryRow("Active", `${display(projection.command_centre?.enabled_strategy_instances)} strategy instance(s)`),
    summaryRow("Decision review", `${display(facts.length)} checkpoint(s) available`),
    summaryRow("Open focus", selected ? `${selected.identity.strategy} ${selected.identity.instrument}` : "No strategy selected"),
    summaryRow("Alerts", alerts.length ? `${alerts.length} item(s)` : "Clear"),
  ].join("");

  const authoritySummary = document.getElementById("authoritySummary");
  authoritySummary.innerHTML = renderKeyValuePairs({
    Session: projection.system?.session,
    "Broker order authority": projection.system?.broker_order_authority,
    "System state": projection.command_centre?.system_state,
    "Market state": projection.command_centre?.market_state,
    "Projection hash": shortenHash(projection.projection_hash),
    "Decision explainability facts": facts.length,
    "Unprotected positions": projection.command_centre?.unprotected_positions,
  });

  const alertsPanel = document.getElementById("commandCentreAlerts");
  alertsPanel.innerHTML = "";
  const criticalRows = projection.command_centre?.critical_alert_rows || [];
  if (!criticalRows.length) {
    alertsPanel.appendChild(panel("No critical alerts", { Status: "Clear" }));
  } else {
    criticalRows.forEach(item => alertsPanel.appendChild(panel(item.code || "Alert", item)));
  }

  const eventsPanel = document.getElementById("commandCentreEvents");
  eventsPanel.innerHTML = "";
  const events = projection.command_centre?.recent_operational_events || [];
  if (!events.length) {
    eventsPanel.appendChild(panel("No recent events", { Status: "No events available" }));
  } else {
    events.slice(0, 6).forEach(item => eventsPanel.appendChild(panel(item.instrument || "Event", item)));
  }

  populatePanelList("commandCentreTrades", projection.command_centre?.active_trades || [], item => ({
    title: `${item.strategy || "Strategy"} ${item.instrument || ""}`.trim(),
    data: {
      Contract: item.contract,
      Status: item.status,
      Protection: item.protection,
      "Current P&L": item.pnl,
    },
  }), "No active trades", { Status: "No open position rows in this snapshot" });

  populatePanelList("commandCentreActions", projection.command_centre?.pending_actions || [], item => ({
    title: `${item.instrument || "Action"} / ${item.action || "Pending"}`,
    data: {
      Strategy: item.strategy_instance_id,
      Reason: item.reason,
    },
  }), "No pending actions", { Status: "No operator action queue in this snapshot" });

  const strategySummaryRows = projection.command_centre?.strategy_definition_summaries || [];
  populatePanelList("commandCentreStrategyHealth", strategySummaryRows.length ? strategySummaryRows : (projection.command_centre?.strategy_health || []), item => ({
    title: item.strategy_code ? `${item.strategy_code} / ${item.display_name}` : `${item.strategy || "Strategy"} ${item.instrument || ""}`.trim(),
    data: {
      Health: item.health,
      Evidence: item.evidence_quality || item.evidence,
      "Entry available": item.entry_available_count ?? item.current_action,
      "Open positions": item.open_count ?? "",
      "Realized P&L": item.realized_pnl ?? "",
      "Unrealized P&L": item.unrealized_pnl ?? "",
    },
  }), "No strategy health rows", { Status: "No strategy summary rows available" });

  populatePanelList("commandCentreTimeline", projection.command_centre?.market_session_timeline || [], item => ({
    title: `${item.time || "Time"} / ${item.event || "Event"}`,
    data: {
      Status: item.status,
    },
  }), "No session timeline", { Status: "No session timeline available" });
}

function renderStrategyRail() {
  const groups = state.projection?.navigation?.strategy_groups || [];
  const definitionRows = state.projection?.strategy_definitions || [];
  const search = document.getElementById("strategyRailSearch").value.trim().toLowerCase();
  document.getElementById("strategyCount").textContent = String((state.projection?.strategy_instances || []).length);
  const rail = document.getElementById("strategyRail");
  rail.innerHTML = groups
    .filter(group => !search || JSON.stringify(group).toLowerCase().includes(search))
    .map(group => `
      <div class="rail-group">
        <div class="rail-group-title">${escapeHtml(group.family)}</div>
        <div class="rail-group-list">
          ${group.definitions.map(definition => {
            const selected = definition.strategy_definition_id === state.selectedDefinitionId;
            const summary = definitionRows.find(item => item.strategy_definition_id === definition.strategy_definition_id);
            const counts = definition.status_counts || {};
            return `
              <button type="button" class="strategy-rail-item ${selected ? "is-selected" : ""}" data-definition-id="${definition.strategy_definition_id}">
                <span class="rail-topline">
                  <strong>${escapeHtml(definition.strategy_code)}</strong>
                  ${badgeMarkup("neutral", `${display(definition.enabled_count)} enabled`)}
                </span>
                <span class="rail-meta">${escapeHtml(definition.display_name || definition.strategy_code)}</span>
                <span class="rail-meta">Entry ${display(counts.entry_available || 0)} | Open ${display(counts.open_positions || 0)} | Blocked ${display(counts.blocked || 0)}</span>
                <span class="rail-meta">Supported ${display(summary?.supported_count || definition.supported_count || definition.enabled_count)}</span>
              </button>
            `;
          }).join("")}
        </div>
      </div>
    `).join("");
  rail.querySelectorAll("[data-definition-id]").forEach(item => {
    item.addEventListener("click", () => {
      state.selectedDefinitionId = item.dataset.definitionId;
      state.selectedStrategyId = null;
      state.activeTab = "opportunity-queue";
      syncRouteState();
      render();
    });
  });
}

function renderWorkbench() {
  const projection = state.projection;
  const definitions = projection?.strategy_definitions || [];
  const selectedDefinition = getSelectedDefinition();
  const filtered = getFilteredStrategyRows({ ignorePaging: true });
  const paged = getPagedStrategyRows(filtered);
  document.getElementById("strategyWorkbenchSummary").innerHTML = [
    badgeMarkup("neutral", `${definitions.length} strategy definition(s)`),
    badgeMarkup("neutral", `${(projection?.strategy_instances || []).length} configured instance(s)`),
    badgeMarkup("good", `${projection?.strategy_status_counts?.global?.open_positions || 0} open position(s)`),
    badgeMarkup("warn", `${projection?.strategy_status_counts?.global?.blocked || 0} blocked`),
    badgeMarkup("neutral", `${projection?.strategy_status_counts?.global?.no_trade || 0} no trade`),
  ].join("");
  renderStrategyFamilies();
  renderStrategyDefinitionTable(definitions);
  renderStrategyQuickViews(getQuickViewsForSelectedDefinition());
  renderStrategyInstanceList(selectedDefinition, filtered, paged);
}

function renderExplorer() {
  const selected = getSelectedStrategy();
  const title = document.getElementById("explorerTitle");
  const healthBadge = document.getElementById("explorerHealth");
  const summary = document.getElementById("selectedStrategySummary");
  const flow = document.getElementById("selectedStrategyFlow");
  const badge = document.getElementById("selectedStrategyBadge");
  const tabBar = document.getElementById("explainTabs");
  const panel = document.getElementById("explainPanel");
  const context = document.getElementById("selectedStrategyContext");
  const checklist = document.getElementById("selectedStrategyChecklist");
  const definitionTitle = document.getElementById("selectedDefinitionTitle");
  const definitionSummary = document.getElementById("selectedDefinitionSummary");
  const instanceNavigator = document.getElementById("selectedInstanceNavigator");

  if (!selected) {
    title.textContent = "No strategy instance selected";
    healthBadge.className = "badge badge-neutral";
    healthBadge.textContent = "Awaiting operator selection";
    badge.textContent = "";
    summary.innerHTML = `
      <div class="empty-state">
        <strong>No strategy instance selected.</strong><br>
        Choose an opportunity from Opportunity Queue.
        <div class="empty-actions">
          <button type="button" class="action-button" id="openOpportunityQueueButton">Open Opportunity Queue</button>
        </div>
      </div>
    `;
    context.innerHTML = "";
    checklist.innerHTML = "";
    definitionTitle.textContent = "Selected strategy definition";
    definitionSummary.innerHTML = "";
    instanceNavigator.innerHTML = "";
    flow.innerHTML = "";
    tabBar.innerHTML = "";
    panel.innerHTML = "";
    document.getElementById("openOpportunityQueueButton")?.addEventListener("click", () => {
      state.activeTab = "opportunity-queue";
      syncRouteState();
      render();
    });
    return;
  }

  const sectionModel = getExplainSectionModel(selected);
  const selectedDefinition = getSelectedDefinition();
  const relatedInstances = getInstancesForCurrentDefinition();
  title.textContent = `${selected.identity.strategy} ${selected.identity.instrument} decision path`;
  healthBadge.className = `badge ${badgeClass(getHealthTone(selected.state.health))}`;
  healthBadge.textContent = selected.state.health || "Health unavailable";
  badge.innerHTML = `${badgeMarkup("neutral", selected.state.runtime_stage || "Runtime stage unavailable")} ${badgeMarkup("neutral", selected.state.evidence_quality || "Evidence unavailable")}`;
  context.innerHTML = renderDecisionContextStrip(selected);
  checklist.innerHTML = renderDecisionChecklistCompact(selected);
  definitionTitle.textContent = selectedDefinition
    ? `${selectedDefinition.strategy_code} strategy set`
    : "Selected strategy definition";
  definitionSummary.innerHTML = renderDefinitionSummaryChips(selectedDefinition, relatedInstances);
  instanceNavigator.innerHTML = renderInstanceNavigator(relatedInstances, selected.identity.instance);
  instanceNavigator.querySelectorAll("[data-instance-switch]").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedStrategyId = button.dataset.instanceSwitch;
      state.explainTab = "overview";
      syncRouteState();
      render();
    });
  });

  summary.innerHTML = [
    metricTile("Monthly", selected.state.monthly_status),
    metricTile("Branch", selected.state.branch),
    metricTile("Contract", selected.plan.selected_contract),
    metricTile("Entry", selected.plan.base_entry),
    metricTile("Target", selected.plan.target),
    metricTile("SL", selected.plan.original_sl),
  ].join("");

  flow.innerHTML = REQUIRED_STAGE_KEYS.map(key => {
    const item = sectionModel[key];
    return `
      <button type="button" class="flow-step compact-step tone-${item.statusTone} ${state.explainTab === key ? "is-active" : ""}" data-explain-tab="${key}">
        <span class="flow-label">${escapeHtml(item.shortLabel || item.label)}</span>
        <span class="flow-state">${escapeHtml(item.statusLabel)}</span>
      </button>
    `;
  }).join("");
  flow.querySelectorAll("[data-explain-tab]").forEach(button => {
    button.addEventListener("click", () => {
      state.explainTab = button.dataset.explainTab;
      renderExplorer();
    });
  });

  tabBar.innerHTML = EXPLAIN_TABS.map(tab => `
    <button type="button" class="subtab ${state.explainTab === tab.key ? "is-active" : ""}" data-explain-tab="${tab.key}">
      ${escapeHtml(tab.label)}
    </button>
  `).join("");
  tabBar.querySelectorAll("[data-explain-tab]").forEach(button => {
    button.addEventListener("click", () => {
      state.explainTab = button.dataset.explainTab;
      renderExplorer();
    });
  });

  panel.innerHTML = renderExplainPanel(selected, sectionModel);
  wireManualComparisonInputs(selected);
}

function renderDecisionExplorerWorkspace() {
  const selected = getSelectedStrategy();
  const title = document.getElementById("engineeringExplorerTitle");
  const healthBadge = document.getElementById("engineeringExplorerHealth");
  const summary = document.getElementById("engineeringExplorerSummary");
  const flow = document.getElementById("engineeringExplorerFlow");
  const tabBar = document.getElementById("engineeringTabs");
  const panel = document.getElementById("engineeringPanel");
  if (!selected) {
    title.textContent = "Select a strategy";
    healthBadge.className = "badge badge-neutral";
    healthBadge.textContent = "No strategy selected";
    summary.innerHTML = `<div class="empty-state">Select one strategy to inspect the engineering decision flow.</div>`;
    flow.innerHTML = "";
    tabBar.innerHTML = "";
    panel.innerHTML = "";
    return;
  }
  const sectionModel = getExplainSectionModel(selected);
  title.textContent = `${selected.identity.strategy} ${selected.identity.instrument} engineering decision flow`;
  healthBadge.className = `badge ${badgeClass(getHealthTone(selected.state.health))}`;
  healthBadge.textContent = selected.state.health_label || selected.state.health;
  summary.innerHTML = [
    metricTile("Monthly Status", selected.state.monthly_status_label || selected.state.monthly_status),
    metricTile("Branch", selected.state.branch_label || selected.state.branch),
    metricTile("Contract", selected.plan.selected_contract),
    metricTile("Entry Eligibility", selected.state.entry_eligibility_label || selected.state.entry_eligibility),
    metricTile("Evidence", selected.state.evidence_quality_label || selected.state.evidence_quality),
    metricTile("Decision Facts", getFactsForStrategy(selected.identity.instance).length),
  ].join("");
  flow.innerHTML = REQUIRED_STAGE_KEYS.map(key => {
    const item = sectionModel[key];
    return `
      <button type="button" class="flow-step tone-${item.statusTone}" data-engineering-tab="${key}">
        <span class="flow-label">${escapeHtml(item.label)}</span>
        <span class="flow-copy">${escapeHtml(item.caption)}</span>
      </button>
    `;
  }).join("");
  flow.querySelectorAll("[data-engineering-tab]").forEach(button => {
    button.addEventListener("click", () => {
      state.explainTab = button.dataset.engineeringTab;
      renderDecisionExplorerWorkspace();
    });
  });
  tabBar.innerHTML = EXPLAIN_TABS.map(tab => `
    <button type="button" class="subtab ${state.explainTab === tab.key ? "is-active" : ""}" data-engineering-tab="${tab.key}">
      ${escapeHtml(tab.label)}
    </button>
  `).join("");
  tabBar.querySelectorAll("[data-engineering-tab]").forEach(button => {
    button.addEventListener("click", () => {
      state.explainTab = button.dataset.engineeringTab;
      renderDecisionExplorerWorkspace();
    });
  });
  panel.innerHTML = renderExplainPanel(selected, sectionModel);
  wireManualComparisonInputs(selected);
}

function renderExplainPanel(strategy, sectionModel) {
  const section = sectionModel[state.explainTab] || sectionModel.overview;
  return `
    <div class="panel-banner compact-banner tone-${section.statusTone}">
      <div>
        <h3>${escapeHtml(section.label)}</h3>
        <p>${escapeHtml(section.caption)}</p>
      </div>
      ${badgeMarkup(section.statusTone, section.statusLabel)}
    </div>
    ${section.body}
  `;
}

function getExplainSectionModel(strategy) {
  const facts = getFactsForStrategy(strategy.identity.instance);
  const monthlyFact = facts.find(item => item.stage === "MONTHLY_STATUS");
  const contractFact = facts.find(item => item.stage === "CONTRACT_SELECTION");
  const planFact = facts.find(item => item.stage === "PLAN_COMPOSITION");
  const entryFact = facts.find(item => item.stage === "ENTRY_ELIGIBILITY");
  const actionFact = facts.find(item => item.stage === "CURRENT_ACTION");
  const candidateFacts = contractFact?.candidate_evidence || {};
  const evaluatedContracts = candidateFacts.evaluated_contracts || [];
  const rejectedCandidates = candidateFacts.rejected_candidates || [];
  const monthlyDerivation = monthlyFact?.candidate_evidence?.derivation || {};
  const timelineFacts = facts.length ? facts : [];
  const rawPrices = planFact?.output_value?.raw_prices || {};
  const normalizedPrices = planFact?.output_value?.normalized_prices || {};
  const formulaCatalog = planFact?.intermediate_values?.formula_catalog || contractFact?.candidate_evidence?.formula_catalog || {};
  const reconstruction = entryFact?.candidate_evidence?.reconstruction || {};
  const manualRows = buildManualComparisonRows(strategy);

  return {
    overview: buildSection(
      "Decision overview",
      "What TFIS decided, the current state, and whether the strategy is fully explained.",
      getStrategyCompleteness(strategy).statusTone,
      getStrategyCompleteness(strategy).label,
      renderOverviewExplain(strategy)
    ),
    "monthly-status": buildSection(
      "Monthly Status",
      "Higher-timeframe market bias before branch selection.",
      monthlyFact ? "good" : strategy.state.monthly_status ? "warn" : "bad",
      monthlyFact ? "Explained" : strategy.state.monthly_status ? "Output visible" : "Missing",
      `
        ${renderMonthlyStatusHero(strategy, monthlyDerivation, monthlyFact)}
        ${renderMonthlyDerivationTrail(monthlyDerivation, strategy)}
        ${renderMonthlyReferenceTable(monthlyDerivation.references || {})}
        ${renderMonthlyStatusVerificationGuide(strategy, monthlyDerivation)}
      `
    ),
    branch: buildSection(
      "Branch mapping",
      "How market bias mapped into the strategy branch.",
      strategy.state.branch ? (facts.length ? "neutral" : "warn") : "bad",
      strategy.state.branch ? (facts.length ? "Available" : "Output only") : "Missing",
      `
        ${renderKeyFactsPanel({
          "Monthly Status input": strategy.state.monthly_status,
          "Selected branch": strategy.state.branch,
          "Call / Put": inferOptionChoice(strategy.state.branch),
          "Bull / Bear": inferDirectionalChoice(strategy.state.branch),
          "Rule trace": facts.length ? "Available through source-trace and contract-selection facts" : "Dedicated branch mapping fact not emitted",
        }, "Branch selection")}
        ${renderKeyFactsPanel({
          "What this means operationally": buildBranchNarrative(strategy.state.branch),
          "What can be checked now": "Monthly Status returned by backend and final branch selected by backend",
          "What is still missing": "Dedicated branch-policy explanation fact with authoritative mapping steps",
        }, "Operator interpretation")}
      `
    ),
    "market-structure": buildSection(
      "Market Structure",
      "Reference levels and timing windows used by the plan.",
      Object.keys(strategy.plan.market_references || {}).length ? "neutral" : "bad",
      Object.keys(strategy.plan.market_references || {}).length ? "Available" : "Missing",
      `
        ${renderKeyFactsPanel({
          "ORPT time": strategy.plan.orpt,
          "RC time": strategy.plan.rc,
          "Opening context": strategy.execution.opening_context,
          "ORPT state": strategy.execution.orpt_state,
          "RC state": strategy.execution.rc_state,
        }, "Timing and state")}
        ${renderReferenceGrid(strategy.plan.market_references || {}, "Market references")}
      `
    ),
    "contract-selection": buildSection(
      "Contract Selection",
      "Selected option plus candidate and rejection evidence.",
      contractFact ? "good" : strategy.plan.selected_contract ? "warn" : "bad",
      contractFact ? "Explained" : strategy.plan.selected_contract ? "Selected only" : "Missing",
      `
        ${renderKeyFactsPanel({
          "Selected contract": strategy.plan.selected_contract,
          "Expiry candidates": display(strategy.plan.expiry_candidates),
          "Branch": strategy.state.branch,
          "Candidate count": evaluatedContracts.length || strategy.plan.candidate_contract_count || 0,
          "Rule": contractFact?.rule_id,
          "Workbook": contractFact?.workbook_source,
        }, "Selection summary")}
        ${renderKeyFactsPanel({
          "Selection source": candidateFacts.selection_source,
          "Workbook row": candidateFacts.workbook_row_id,
          "Source cells": display(candidateFacts.source_cells),
          "Selection report": candidateFacts.selection_report_path,
          "Selection quality": strategy.state.evidence_quality,
          "Operator conclusion": contractFact ? "TFIS recorded a contract-selection evidence packet for this decision." : "Only the final selected contract is visible in this snapshot.",
        }, "Operator review")}
        ${renderKeyFactsPanel({
          "Selected premium": contractFact?.output_value?.premium || strategy.plan.premium,
          "Selected OI": contractFact?.output_value?.oi || strategy.plan.oi,
          "Selected strike": contractFact?.output_value?.selected_strike,
          "Selected option type": contractFact?.output_value?.selected_option_type,
          "Selected expiry": contractFact?.output_value?.selected_expiry,
          "Qualification phase": contractFact?.output_value?.qualification_phase,
        }, "Why this contract qualified")}
        ${renderKeyFactsPanel({
          "Selection logic": "TFIS evaluates actual listed contracts only. It checks branch, expiry, option side, strike range, OI, and premium filters before freezing one final contract.",
          "Evidence origin": summarizeObject(candidateFacts.evidence_origin || {}),
          "Selected-option references": summarizeObject(candidateFacts.selected_option_references || {}),
          "Formula catalog": summarizeObject(candidateFacts.formula_catalog || {}),
        }, "How to validate manually")}
        ${renderCandidateTables(evaluatedContracts, rejectedCandidates)}
        ${renderExplainFactCards([contractFact])}
      `
    ),
    entry: buildSection(
      "Entry Calculation",
      "Entry price, normalized price, and supporting rule.",
      planFact ? "good" : strategy.plan.base_entry ? "warn" : "bad",
      planFact ? "Explained" : strategy.plan.base_entry ? "Output visible" : "Missing",
      `
        ${renderKeyFactsPanel({
          "Displayed entry": strategy.plan.base_entry,
          "Raw entry": rawPrices.base_entry || "Not emitted in this snapshot",
          "Normalized entry": normalizedPrices.base_entry || strategy.plan.base_entry,
          "Selected contract": strategy.plan.selected_contract,
          "Rule": planFact?.rule_id || "READ_MODEL_PLAN_VALUES",
          "Formula status": Object.keys(formulaCatalog).length ? "Formula catalog and raw vs normalized outputs are available." : "Final output visible; intermediate formula catalog not emitted.",
        }, "Entry values")}
        ${renderKeyFactsPanel({
          "Inputs visible here": summarizeObject(strategy.plan.market_references || {}),
          "Target returned by backend": strategy.plan.target,
          "Original SL returned by backend": strategy.plan.original_sl,
          "Base-entry formula": formulaCatalog.base_entry,
          "Target formula": formulaCatalog.target,
          "Original-SL formula": formulaCatalog.original_sl,
          "Revised-entry formula": formulaCatalog.revised_entry,
          "Revised-SL formula": formulaCatalog.revised_sl,
        }, "Explanation quality")}
        ${renderExplainFactCards([planFact])}
      `
    ),
    "orpt-rc": buildSection(
      "ORPT / RC",
      "Opening cutoff and recalculation state.",
      entryFact || strategy.execution.orpt_state || strategy.execution.rc_state ? (entryFact ? "good" : "warn") : "bad",
      entryFact ? "Explained" : "Partial",
      `
        ${renderKeyFactsPanel({
          "ORPT result": reconstruction.orpt_result || strategy.execution.orpt_state,
          "RC result": reconstruction.rc_result || strategy.execution.rc_state,
          "Current entry state": reconstruction.current_entry_state || strategy.state.runtime_stage,
          "Activation time": reconstruction.normal_entry?.activation_time,
          "Trigger price": reconstruction.normal_entry?.trigger_price,
          "Breach timestamp": reconstruction.normal_entry?.breach_timestamp,
        }, "Eligibility state")}
        ${renderKeyFactsPanel({
          "ORPT clock": strategy.plan.orpt,
          "RC clock": strategy.plan.rc,
          "Entry eligibility label": strategy.state.entry_eligibility_label,
          "Current operator meaning": explainEntryState(reconstruction.current_entry_state || strategy.state.runtime_stage),
        }, "Operator interpretation")}
        ${renderExplainFactCards([entryFact])}
      `
    ),
    protection: buildSection(
      "Target and stop-loss",
      "Target and protection linked to current position state.",
      strategy.plan.target || strategy.plan.original_sl ? "neutral" : "bad",
      strategy.plan.target || strategy.plan.original_sl ? "Available" : "Missing",
      `
        ${renderKeyFactsPanel({
          "Target": strategy.plan.target,
          "Original SL": strategy.plan.original_sl,
          "Active protection": strategy.position.active_protection || strategy.position.active_sl || strategy.position.target,
          "Protection status": strategy.position.protection_status,
          "Protection generation": strategy.execution.protection_generation,
        }, "Protection values")}
        ${renderKeyFactsPanel({
          "Raw target": rawPrices.target,
          "Normalized target": normalizedPrices.target || strategy.plan.target,
          "Raw SL": rawPrices.original_sl,
          "Normalized SL": normalizedPrices.original_sl || strategy.plan.original_sl,
          "Raw revised entry": rawPrices.revised_entry,
          "Normalized revised entry": normalizedPrices.revised_entry,
          "Raw revised SL": rawPrices.revised_sl,
          "Normalized revised SL": normalizedPrices.revised_sl,
        }, "Raw versus normalized")}
      `
    ),
    "order-position": buildSection(
      "Order and Position",
      "Order, fill, quantity, and position health.",
      strategy.execution.order_state || strategy.position.health ? "neutral" : "bad",
      strategy.execution.order_state || strategy.position.health ? "Available" : "Missing",
      `
        ${renderKeyFactsPanel({
          "Order state": strategy.execution.order_state,
          "Fill state": strategy.execution.fill_state,
          "Order purpose": strategy.execution.order_purpose,
          "Position cycle": strategy.position.position_cycle,
          "Fresh / carried": strategy.position.fresh_or_carried,
          "Remaining quantity": strategy.position.remaining_quantity,
          "Exit deadline": strategy.position.exit_deadline,
          "Latest event": strategy.execution.latest_event,
        }, "Order and position state")}
        ${renderExplainFactCards([actionFact])}
      `
    ),
    pnl: buildSection(
      "P&L",
      "Realized and unrealized P&L from the current model.",
      strategy.accounting ? "neutral" : "bad",
      strategy.accounting ? "Available" : "Missing",
      `
        ${renderKeyFactsPanel({
          "Accounting quality": strategy.accounting.accounting_quality,
          "Charges quality": strategy.accounting.charges_quality,
          "Trade classification": strategy.accounting.trade_classification,
          "Realized P&L": strategy.accounting.realized_pnl,
          "Unrealized P&L": strategy.accounting.unrealized_pnl,
          "Average entry": strategy.position.average_entry,
          "Mark": strategy.position.mark,
          "Quantity": strategy.position.quantity,
        }, "P&L inputs and outputs")}
      `
    ),
    timeline: buildSection(
      "Timeline",
      "Chronological immutable events for this strategy instance.",
      timelineFacts.length ? "neutral" : "warn",
      timelineFacts.length ? "Available" : "Limited",
      renderTimeline(timelineFacts, strategy)
    ),
    manual: buildSection(
      "Manual Comparison",
      "Manual comparison only. Runtime truth does not change here.",
      "neutral",
      "Validation only",
      renderManualComparison(strategy, manualRows)
    ),
    "source-trace": buildSection(
      "Source Trace",
      "Workbook and rule references linked to immutable facts.",
      facts.length ? "neutral" : "warn",
      facts.length ? "Available" : "Limited",
      renderSourceTrace(strategy, facts)
    ),
  };
}

function buildSection(label, caption, statusTone, statusLabel, body) {
  return { label, caption, statusTone, statusLabel, shortLabel: label, body };
}

function getStrategyCompleteness(strategy) {
  const sections = getExplainSectionModelForCompleteness(strategy);
  const missing = sections.filter(item => item.statusTone === "bad").length;
  const limited = sections.filter(item => item.statusTone === "warn").length;
  if (missing) {
    return { label: `${missing} missing`, badgeTone: "bad", statusTone: "bad" };
  }
  if (limited) {
    return { label: `${limited} limited`, badgeTone: "warn", statusTone: "warn" };
  }
  return { label: "Explained", badgeTone: "good", statusTone: "good" };
}

function getExplainSectionModelForCompleteness(strategy) {
  const facts = getFactsForStrategy(strategy.identity.instance);
  const contractFact = facts.find(item => item.stage === "CONTRACT_SELECTION");
  const planFact = facts.find(item => item.stage === "PLAN_COMPOSITION");
  const entryFact = facts.find(item => item.stage === "ENTRY_ELIGIBILITY");
  const actionFact = facts.find(item => item.stage === "CURRENT_ACTION");
  return [
    { key: "monthly-status", label: "Monthly Status", caption: strategy.state.monthly_status || "No monthly status", shortLabel: "MS", statusTone: strategy.state.monthly_status ? (facts.length ? "neutral" : "warn") : "bad", statusLabel: strategy.state.monthly_status ? "Available" : "Missing" },
    { key: "branch", label: "Branch", caption: strategy.state.branch || "No branch", shortLabel: "Branch", statusTone: strategy.state.branch ? (facts.length ? "neutral" : "warn") : "bad", statusLabel: strategy.state.branch ? "Available" : "Missing" },
    { key: "market-structure", label: "Market Structure", caption: strategy.plan.orpt || strategy.plan.rc ? "References and timing visible" : "No timing detail", shortLabel: "Refs", statusTone: Object.keys(strategy.plan.market_references || {}).length ? "neutral" : "bad", statusLabel: Object.keys(strategy.plan.market_references || {}).length ? "Available" : "Missing" },
    { key: "contract-selection", label: "Contract Selection", caption: strategy.plan.selected_contract || "No contract", shortLabel: "Contract", statusTone: contractFact ? "good" : strategy.plan.selected_contract ? "warn" : "bad", statusLabel: contractFact ? "Explained" : strategy.plan.selected_contract ? "Selected only" : "Missing" },
    { key: "entry", label: "Entry", caption: strategy.plan.base_entry || "No entry", shortLabel: "Entry", statusTone: planFact ? "good" : strategy.plan.base_entry ? "warn" : "bad", statusLabel: planFact ? "Explained" : strategy.plan.base_entry ? "Output only" : "Missing" },
    { key: "orpt-rc", label: "ORPT / RC", caption: strategy.execution.orpt_state || "No ORPT state", shortLabel: "Timing", statusTone: entryFact ? "good" : strategy.execution.orpt_state || strategy.execution.rc_state ? "warn" : "bad", statusLabel: entryFact ? "Explained" : "Partial" },
    { key: "protection", label: "Protection", caption: strategy.plan.target || strategy.plan.original_sl ? "Target and SL visible" : "No protection values", shortLabel: "SL", statusTone: strategy.plan.target || strategy.plan.original_sl ? "neutral" : "bad", statusLabel: strategy.plan.target || strategy.plan.original_sl ? "Available" : "Missing" },
    { key: "order-position", label: "Order & Position", caption: strategy.execution.order_state || "No order state", shortLabel: "Position", statusTone: actionFact ? "good" : strategy.execution.order_state || strategy.position.health ? "warn" : "bad", statusLabel: actionFact ? "Explained" : "Partial" },
    { key: "pnl", label: "P&L", caption: strategy.accounting?.realized_pnl || strategy.accounting?.unrealized_pnl ? "Accounting visible" : "No accounting values", shortLabel: "P&L", statusTone: strategy.accounting ? "neutral" : "bad", statusLabel: strategy.accounting ? "Available" : "Missing" },
    { key: "timeline", label: "Timeline", caption: facts.length ? `${facts.length} event(s)` : "No immutable fact sequence", shortLabel: "Timeline", statusTone: facts.length ? "neutral" : "warn", statusLabel: facts.length ? "Available" : "Limited" },
    { key: "source-trace", label: "Source Trace", caption: facts.length ? "Workbook refs visible" : "No fact-backed trace", shortLabel: "Trace", statusTone: facts.length ? "neutral" : "warn", statusLabel: facts.length ? "Available" : "Limited" },
  ];
}

function renderOverviewExplain(strategy) {
  const completeness = getStrategyCompleteness(strategy);
  const facts = getFactsForStrategy(strategy.identity.instance);
  return `
    ${renderKeyFactsPanel({
      Strategy: `${strategy.identity.strategy} ${strategy.identity.instrument}`,
      Account: strategy.identity.account_display_name || strategy.identity.account,
      "Monthly Status": strategy.state.monthly_status,
      Branch: strategy.state.branch,
      "Runtime stage": strategy.state.runtime_stage,
      "Selected contract": strategy.plan.selected_contract,
      "Explainability completeness": completeness.label,
      "Decision fact count": facts.length,
    }, "Decision summary")}
    ${facts.length ? renderExplainFactCards(facts.slice(0, 4)) : renderWarningBox("No immutable stepwise facts were emitted for this strategy in this snapshot. Final outputs are visible, but traceability is limited.")}
  `;
}

function renderReferenceGrid(references, title) {
  const entries = Object.entries(references || {});
  if (!entries.length) {
    return renderWarningBox("No market-reference values were available in the current snapshot.");
  }
  return `
    <div class="detail-block">
      <h4>${escapeHtml(title)}</h4>
      <div class="mini-grid">
        ${entries.map(([key, value]) => metricTile(key, value)).join("")}
      </div>
    </div>
  `;
}

function renderMonthlyStatusHero(strategy, derivation, monthlyFact) {
  const status = strategy.state.monthly_status;
  const plainEnglish = explainMonthlyStatus(status);
  const summary = derivation.reason || "TFIS emitted a final Monthly Status value for this instrument.";
  const evidenceState = derivation.available
    ? "Full trail available"
    : "Summary only";
  const nextAction = "Check Branch next.";
  return `
    <div class="detail-block monthly-hero">
      <div class="monthly-hero-head">
        <div>
          <h4>Monthly decision</h4>
          <p>TFIS decides market bias first, then branch, then contract.</p>
        </div>
        ${badgeMarkup(derivation.available ? "good" : "warn", evidenceState)}
      </div>
      <div class="summary-grid">
        ${summaryTile("Status", display(status))}
        ${summaryTile("Meaning", plainEnglish)}
        ${summaryTile("Driver", summary)}
        ${summaryTile("Next", nextAction)}
      </div>
      <div class="key-value-grid">
        ${renderKeyValuePairs({
          Instrument: strategy.identity.instrument,
          "Eval time": derivation.evaluation_timestamp || strategy.state.last_update,
          "Current month": derivation.current_window_direct_status || "Not recorded",
          "Borrowed context": derivation.borrowed_window_status || "Not used",
          "Lookback used": derivation.lookback_used,
          "Trigger": derivation.trigger_name || "Not recorded",
          "Threshold": derivation.threshold_value || "Not recorded",
          "Rule": derivation.rule_id || monthlyFact?.rule_id || "MONTHLY_STATUS.GENERIC.ENGINE.001",
          "Evidence": evidenceState,
        })}
      </div>
    </div>
  `;
}

function renderMonthlyDerivationTrail(derivation, strategy) {
  if (!derivation || !derivation.available) {
    return `
      ${renderWarningBox(`A full monthly derivation trail is not available for ${strategy.identity.instrument} in this snapshot.`)}
      <div class="detail-block">
        <h4>Operator note</h4>
        <div class="review-list">
          <div class="review-item"><strong>Result available</strong><span>TFIS can continue to branch selection.</span></div>
          <div class="review-item"><strong>Audit trail missing</strong><span>The detailed month-by-month packet was not stored in this snapshot.</span></div>
          <div class="review-item"><strong>Operator stance</strong><span>Treat this as summary-only evidence.</span></div>
        </div>
      </div>
    `;
  }
  const steps = derivation.steps || [];
  if (!steps.length) {
    return renderWarningBox(`Monthly Status is available for ${strategy.identity.instrument}, but the stepwise trail is missing from the current evidence packet.`);
  }
  return `
    <div class="detail-block">
      <h4>Derivation trail</h4>
      <div class="timeline-list">
        ${steps.map(item => `
          <article class="timeline-card">
            <div class="timeline-head">
              <div>
                <strong>Step ${escapeHtml(String(item.step))}: ${escapeHtml(item.title || "Monthly derivation step")}</strong>
                <p>${escapeHtml(item.detail || "No detail available.")}</p>
              </div>
              ${badgeMarkup(getHealthTone(item.result), display(item.result))}
            </div>
            <div class="key-value-grid">
              ${renderKeyValuePairs(item.values || {})}
            </div>
          </article>
        `).join("")}
      </div>
    </div>
  `;
}

function renderMonthlyReferenceTable(references) {
  const entries = Object.entries(references || {});
  if (!entries.length) {
    return "";
  }
  return `
    <div class="detail-block">
      <h4>Reference levels used by the monthly engine</h4>
      ${renderSimpleTable(
        ["Reference", "Value", "Meaning"],
        entries.map(([key, value]) => [key, value, explainMonthlyReference(key)]),
        "No monthly reference levels were present in this snapshot."
      )}
    </div>
  `;
}

function renderMonthlyStatusVerificationGuide(strategy, derivation) {
  return `
    <div class="detail-block">
      <h4>Manual check</h4>
      <div class="review-list">
        <div class="review-item">
          <strong>1. Check levels</strong>
          <span>Validate the monthly and weekly reference values.</span>
        </div>
        <div class="review-item">
          <strong>2. Read the trail</strong>
          <span>Confirm whether TFIS used direct month logic or borrowed context.</span>
        </div>
        <div class="review-item">
          <strong>3. Use it as a gate</strong>
          <span>Monthly Status narrows direction. It does not select the contract.</span>
        </div>
        <div class="review-item">
          <strong>4. Note evidence quality</strong>
          <span>${escapeHtml(derivation.available ? "Full derivation is available." : "Only summary evidence is available here.")}</span>
        </div>
      </div>
      <div class="inline-summary">
        ${badgeMarkup("neutral", monthlyStatusReadingGuide(strategy.state.monthly_status))}
        ${badgeMarkup("neutral", `Next: Branch`)}
        ${badgeMarkup("neutral", `Snapshot: ${display(strategy.state.evidence_quality)}`)}
      </div>
    </div>
  `;
}

function renderCandidateTables(evaluatedContracts, rejectedCandidates) {
  return `
    <div class="detail-block">
      <h4>Evaluated contracts</h4>
      ${renderSimpleTable(
        ["Contract", "Expiry", "Type", "Strike", "Bid", "Ask", "LTP", "OI", "Quality"],
        (evaluatedContracts || []).map(item => [
          item.symbol,
          item.expiry,
          item.option_type,
          item.strike,
          item.bid,
          item.ask,
          item.ltp,
          item.oi,
          `${display(item.source_quality)} / ${display(item.quote_freshness)}`,
        ]),
        "No evaluated-contract rows were emitted for this selection."
      )}
    </div>
    <div class="detail-block">
      <h4>Rejected candidates</h4>
      ${renderSimpleTable(
        ["Contract", "Expiry", "Type", "Strike", "Premium", "OI", "Reason"],
        (rejectedCandidates || []).map(item => [
          item.symbol || item.contract_id,
          item.expiry,
          item.option_type,
          item.strike,
          item.ltp,
          item.oi,
          item.reason,
        ]),
        "No rejected candidates were recorded for this strategy."
      )}
    </div>
  `;
}

function renderExplainFactCards(facts) {
  const list = (facts || []).filter(Boolean);
  if (!list.length) {
    return renderWarningBox("No dedicated immutable calculation facts are available for this section.");
  }
  return `
    <div class="fact-card-grid compact-facts">
      ${list.map(item => `
        <article class="fact-card">
          <div class="fact-head">
            <strong>${escapeHtml(item.stage || "Stage")}</strong>
            ${badgeMarkup(item.rejection_reason ? "warn" : "neutral", item.rule_id || "Rule unavailable")}
          </div>
          <div class="fact-body">
            <div class="fact-inline-list">
              <span><strong>Formula</strong> ${escapeHtml(item.formula_text || "Unavailable")}</span>
              <span><strong>Workbook</strong> ${escapeHtml(item.workbook_source || "Unavailable")}</span>
              <span><strong>Evidence</strong> ${escapeHtml([item.evidence_source, item.evidence_quality, item.evidence_mode].filter(Boolean).join(" / "))}</span>
            </div>
            <div class="key-value-grid compact-grid">
              ${renderKeyValuePairs({
                Inputs: summarizeObject(item.input_values || {}),
                Outputs: summarizeObject(item.output_value || {}),
              })}
            </div>
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

function renderTimeline(facts, strategy) {
  const items = (facts || []).slice().sort((a, b) => String(a.calculation_timestamp || "").localeCompare(String(b.calculation_timestamp || "")));
  const rows = [];
  rows.push({
    timestamp: strategy.state.last_update,
    stage: "SNAPSHOT_STATE",
    result: strategy.state.runtime_stage,
    evidence: strategy.state.evidence_quality,
    detail: `${strategy.state.monthly_status} -> ${strategy.state.branch}`,
  });
  items.forEach(item => rows.push({
    timestamp: item.calculation_timestamp,
    stage: item.stage,
    result: item.rejection_reason || summarizeObject(item.output_value || {}),
    evidence: [item.evidence_source, item.evidence_quality].filter(Boolean).join(" / "),
    detail: item.rule_id || "",
  }));
  return renderSimpleTable(
    ["Timestamp", "Stage", "Result", "Evidence", "Detail"],
    rows.map(item => [item.timestamp, item.stage, item.result, item.evidence, item.detail]),
    "No timeline events were available for this strategy."
  );
}

function buildManualComparisonRows(strategy) {
  return [
    ["monthly_status", "Monthly Status", strategy.state.monthly_status],
    ["branch", "Branch", strategy.state.branch],
    ["selected_contract", "Selected contract", strategy.plan.selected_contract],
    ["entry", "Entry", strategy.plan.base_entry],
    ["target", "Target", strategy.plan.target],
    ["original_sl", "Original SL", strategy.plan.original_sl],
    ["quantity", "Quantity", strategy.position.quantity],
    ["mark", "Mark price", strategy.position.mark],
    ["realized_pnl", "Realized P&L", strategy.accounting?.realized_pnl],
    ["unrealized_pnl", "Unrealized P&L", strategy.accounting?.unrealized_pnl],
  ];
}

function renderManualComparison(strategy, rows) {
  const inputs = state.manualInputs[strategy.identity.instance] || {};
  return `
    <div class="manual-note">Manual values are local to this browser session and do not alter backend truth.</div>
    ${renderSimpleTable(
      ["Field", "Engine value", "Manual value", "Difference", "Match"],
      rows.map(([key, labelText, engineValue]) => {
        const manualValue = inputs[key] || "";
        return [
          labelText,
          display(engineValue),
          `<input type="text" class="manual-input" data-manual-key="${escapeHtml(key)}" value="${escapeHtml(manualValue)}" placeholder="Enter manual value">`,
          escapeHtml(computeManualDifference(engineValue, manualValue)),
          renderMatchBadge(engineValue, manualValue),
        ];
      }),
      "No manual comparison fields are configured."
    )}
  `;
}

function renderMonthlyStatusReview() {
  const selected = getSelectedStrategy();
  const target = document.getElementById("monthlyStatusReviewPanel");
  if (!selected) {
    target.innerHTML = renderWarningBox("Select one strategy to review Monthly Status evidence.");
    return;
  }
  const facts = getFactsForStrategy(selected.identity.instance);
  const monthlyFact = facts.find(item => item.stage === "MONTHLY_STATUS");
  const monthlyDerivation = monthlyFact?.candidate_evidence?.derivation || {};
  target.innerHTML = `
    ${renderKeyFactsPanel({
      "Instrument": selected.identity.instrument,
      "Trading date": selected.identity.session,
      "Final Status": selected.state.monthly_status_label || selected.state.monthly_status,
      "Meaning": explainMonthlyStatus(selected.state.monthly_status),
      "Evidence Quality": selected.state.evidence_quality_label || selected.state.evidence_quality,
      "Evaluation time": monthlyDerivation.evaluation_timestamp,
      "Rule": monthlyDerivation.rule_id || monthlyFact?.rule_id || "READ_MODEL_MONTHLY_STATUS",
      "Trace source": monthlyDerivation.source_path || monthlyDerivation.source || "Runtime snapshot",
    }, "Monthly Status review")}
    ${renderMonthlyDerivationTrail(monthlyDerivation, selected)}
    ${renderMonthlyReferenceTable(monthlyDerivation.references || {})}
    ${renderExplainFactCards([monthlyFact])}
  `;
}

function renderContractSelectionAudit() {
  const selected = getSelectedStrategy();
  const target = document.getElementById("contractSelectionAuditPanel");
  if (!selected) {
    target.innerHTML = renderWarningBox("Select one strategy to inspect contract selection.");
    return;
  }
  target.innerHTML = getExplainSectionModel(selected)["contract-selection"].body;
}

function renderManualValidationWorkspace() {
  const selected = getSelectedStrategy();
  const target = document.getElementById("manualValidationPanel");
  if (!selected) {
    target.innerHTML = renderWarningBox("Select one strategy to compare manual values against engine outputs.");
    return;
  }
  target.innerHTML = getExplainSectionModel(selected).manual.body;
  wireManualComparisonInputs(selected);
}

function renderReplayWorkspace() {
  const target = document.getElementById("replayPanel");
  const selected = getSelectedStrategy();
  target.innerHTML = "";
  if (!selected) {
    target.appendChild(panel("Replay unavailable", { Status: "Select one strategy to inspect replay/reconstruction context." }));
    return;
  }
  target.appendChild(panel("Historical reconstruction", {
    Strategy: `${selected.identity.strategy} ${selected.identity.instrument}`,
    Evidence: selected.state.evidence_quality_label || selected.state.evidence_quality,
    "Current classification": selected.state.runtime_stage_label || selected.state.runtime_stage,
    Availability: "Replay plumbing not exposed in this frontend milestone",
  }));
}

function wireManualComparisonInputs(strategy) {
  const panel = document.getElementById("explainPanel");
  panel.querySelectorAll(".manual-input").forEach(input => {
    input.addEventListener("input", () => {
      const strategyInputs = state.manualInputs[strategy.identity.instance] || {};
      strategyInputs[input.dataset.manualKey] = input.value;
      state.manualInputs[strategy.identity.instance] = strategyInputs;
      if (state.explainTab === "manual") {
        renderExplorer();
      }
    });
  });
}

function renderSourceTrace(strategy, facts) {
  const rows = (facts || []).map(item => [
    item.stage,
    item.rule_id,
    item.workbook_source,
    item.evidence_source,
    item.calculation_timestamp,
    item.decision_id,
  ]);
  return `
    ${renderKeyFactsPanel({
      "Plan hash": strategy.plan.plan_hash,
      "Read model hash": strategy.read_model_hash,
      "Selected contract": strategy.plan.selected_contract,
      "Strategy version": strategy.identity.version,
    }, "Snapshot identifiers")}
    ${renderSimpleTable(
      ["Stage", "Rule", "Workbook / source", "Evidence source", "Timestamp", "Decision id"],
      rows,
      "No source-trace rows are available in the current snapshot."
    )}
  `;
}

function populatePanelList(id, items, mapFn, emptyTitle, emptyData) {
  const target = document.getElementById(id);
  target.innerHTML = "";
  if (!(items || []).length) {
    target.appendChild(panel(emptyTitle, emptyData));
    return;
  }
  items.forEach(item => {
    const mapped = mapFn(item);
    target.appendChild(panel(mapped.title, mapped.data));
  });
}

function renderLedger() {
  renderOrders();
  renderPositions();
}

function formatLots(item) {
  const quantity = display(item.requested_quantity || item.quantity || "");
  const lots = item.lots ? `${display(item.lots)} lot${Number(item.lots) === 1 ? "" : "s"}` : "";
  const lotSize = item.lot_size ? `${display(item.lot_size)}/lot` : "";
  return [quantity, lots, lotSize].filter(Boolean).join(" · ");
}

function formatDateTime(value) {
  if (!value) return "";
  const raw = String(value);
  if (raw.includes("T")) {
    const [date, time] = raw.split("T");
    return `${date} ${time.replace("Z", "").slice(0, 8)}`;
  }
  return raw.replace(".400000", "").replace(".000000", "");
}

function formatOpenPnl(item) {
  const realized = Number(item.realized_pnl || 0);
  const unrealized = Number(item.unrealized_pnl || 0);
  const total = realized + unrealized;
  const parts = [`${total.toFixed(2)}`];
  if (unrealized) parts.push(`U ${display(item.unrealized_pnl)}`);
  if (realized) parts.push(`R ${display(item.realized_pnl)}`);
  return parts.join(" · ");
}

function renderOrders() {
  const projection = state.projection;
  const orders = projection.orders || [];
  const summary = document.getElementById("ordersSummary");
  summary.innerHTML = [
    badgeMarkup("neutral", `${orders.length} working order(s)`),
    badgeMarkup("good", `${orders.filter(item => item.state === "FILLED_INTERNAL").length} filled`),
    badgeMarkup("warn", `${orders.filter(item => item.warning_or_error || item.failure).length} with warning`),
    badgeMarkup("neutral", `${orders.filter(item => item.state === "READY_INTERNAL").length} waiting for trigger`),
  ].join("");
  renderTable("ordersTable", orders.map(o => [
    o.account_display_name || o.account,
    o.order_name || `${o.instrument} ${o.side || ""} Entry`.trim(),
    `${o.strategy}${o.strategy_display_name ? ` · ${o.strategy_display_name}` : ""}`,
    o.instrument,
    o.contract,
    `${o.side || ""} ${o.purpose_label || o.purpose || ""}`.trim(),
    formatLots(o),
    o.price,
    o.target,
    o.active_sl,
    formatDateTime(o.entry_time || o.time),
    o.status_label || o.state,
    o.latest_event,
    o.warning_or_error || o.failure || "No warning",
  ]));
}

function renderPositions() {
  const projection = state.projection;
  const positions = projection.positions || [];
  const summary = document.getElementById("positionsSummary");
  summary.innerHTML = [
    badgeMarkup("neutral", `${positions.length} open position(s)`),
    badgeMarkup("good", `${positions.filter(item => item.health === "OPEN_PROTECTED").length} protected`),
    badgeMarkup("warn", `${positions.filter(item => item.protection_status !== "PROTECTED").length} missing protection`),
    badgeMarkup("neutral", `${positions.filter(item => item.fresh_or_carried === "CARRIED").length} carried overnight`),
  ].join("");
  renderTable("positionsTable", positions.map(o => [
    o.account_display_name || o.account,
    o.position_name || `${o.instrument} ${o.side || ""} Position`.trim(),
    `${o.strategy}${o.strategy_display_name ? ` · ${o.strategy_display_name}` : ""}`,
    o.instrument,
    o.contract,
    `${o.side || ""}${o.fresh_or_carried_label ? ` · ${o.fresh_or_carried_label}` : ""}`,
    formatLots(o),
    formatDateTime(o.entry_time),
    o.average_entry,
    o.mark,
    o.target,
    o.active_sl,
    formatOpenPnl(o),
    o.exit_deadline,
    o.health_label || o.health,
  ]));
}

function renderAccounts() {
  const projection = state.projection;
  const accountsPanel = document.getElementById("accountsPanel");
  const configPanel = document.getElementById("accountConfigPanel");
  accountsPanel.innerHTML = "";
  configPanel.innerHTML = "";
  (projection.accounts || []).forEach(account => {
    accountsPanel.appendChild(panel(account.display_name || account.account_reference, {
      Status: projection.state_labels?.[account.status]?.label || account.status,
      "Accepted instances": account.accepted_instances?.length,
      "Rejected instances": account.rejected_instances?.length,
      "Available margin": account.limits?.available_margin,
      "Reserved margin": account.limits?.reserved_margin,
      "Used margin": account.usage?.used_margin,
      "Margin usage %": account.usage?.margin_usage_pct,
    }));
    configPanel.appendChild(panel(account.display_name || account.account_reference, {
      Reference: account.account_reference,
      Broker: account.limits?.broker,
      Environment: account.limits?.environment,
      "Default account": account.limits?.default_account,
      "Read only / order authorised": account.limits?.read_only_or_order_authorised,
      "Data only or trading": account.limits?.data_only_or_trading,
      "Starting capital": account.limits?.starting_capital,
      "Simulated balance": account.limits?.simulated_balance,
      "Daily loss limit": account.limits?.daily_loss_limit,
      "Maximum margin usage": account.limits?.maximum_account_margin_usage_pct,
      "Maximum new entries": account.limits?.maximum_new_entries_per_session,
      "Maximum concurrent positions": account.limits?.maximum_concurrent_positions,
      "Save mode": "Internal paper local only (contract only)",
    }));
  });
}

function renderRisk() {
  const riskPanel = document.getElementById("riskPanel");
  const worstPositionPanel = document.getElementById("worstPositionPanel");
  const aggregate = state.projection?.risk?.aggregate || {};
  const worst = state.projection?.risk?.worst_position || {};
  riskPanel.innerHTML = "";
  worstPositionPanel.innerHTML = "";
  riskPanel.appendChild(panel("Aggregate Risk", aggregate));
  (state.projection?.risk?.per_account || []).forEach(item => {
    riskPanel.appendChild(panel(item.account, item));
  });
  worstPositionPanel.appendChild(panel(worst.instrument || "No worst position", worst));
}

function renderExplainabilityLibrary() {
  const facts = state.projection?.decision_explanations || [];
  const term = document.getElementById("explainabilityFilter").value.trim().toLowerCase();
  const filtered = facts.filter(item => JSON.stringify(item).toLowerCase().includes(term));
  document.getElementById("explainabilitySummary").innerHTML = [
    badgeMarkup("neutral", `${facts.length} total facts`),
    badgeMarkup("neutral", `${filtered.length} shown`),
    badgeMarkup(filtered.some(item => item.rejection_reason) ? "warn" : "good", filtered.some(item => item.rejection_reason) ? "Contains rejected stages" : "No rejected stages shown"),
  ].join("");
  renderTable("explainabilityTable", filtered.map(item => [
    item.strategy_instance_id,
    item.instrument,
    item.stage,
    item.rule_id,
    item.workbook_source,
    item.formula_text,
    summarizeObject(item.input_values || {}),
    summarizeObject(item.intermediate_values || {}),
    summarizeObject(item.output_value || {}),
    summarizeObject(item.candidate_evidence?.rejected_candidates || []),
    [item.evidence_source, item.evidence_quality, item.evidence_mode].filter(Boolean).join(" / "),
    item.rejection_reason || item.output_value?.current_entry_state || "PASS",
  ]), { multiline: true });
}

function renderEngineeringExplainabilityLibrary() {
  const source = document.getElementById("engineeringExplainabilityFilter");
  if (!source) return;
  const facts = state.projection?.decision_explanations || [];
  const term = source.value.trim().toLowerCase();
  const filtered = facts.filter(item => JSON.stringify(item).toLowerCase().includes(term));
  document.getElementById("engineeringExplainabilitySummary").innerHTML = [
    badgeMarkup("neutral", `${facts.length} total facts`),
    badgeMarkup("neutral", `${filtered.length} shown`),
    badgeMarkup("neutral", "Engineering detail view"),
  ].join("");
  renderTable("engineeringExplainabilityTable", filtered.map(item => [
    item.strategy_instance_id,
    item.instrument,
    item.stage,
    item.rule_id,
    item.workbook_source,
    item.formula_text,
    summarizeObject(item.input_values || {}),
    summarizeObject(item.intermediate_values || {}),
    summarizeObject(item.output_value || {}),
    summarizeObject(item.candidate_evidence?.rejected_candidates || []),
    [item.evidence_source, item.evidence_quality, item.evidence_mode].filter(Boolean).join(" / "),
    item.rejection_reason || item.output_value?.current_entry_state || "PASS",
  ]), { multiline: true });
}

function renderHistoricalTrades() {
  const trades = state.projection?.historical_trades || [];
  const summary = document.getElementById("historicalSummary");
  summary.innerHTML = [
    badgeMarkup("neutral", `${trades.length} trade row(s)`),
    badgeMarkup("good", `${trades.filter(item => item.exit_time).length} closed`),
    badgeMarkup("neutral", `${trades.filter(item => !item.exit_time).length} open`),
    badgeMarkup("warn", `${trades.filter(item => item.explanation_completeness !== "Available").length} limited explanation`),
  ].join("");
  const rows = trades.map(item => [
    item.strategy,
    item.account,
    item.instrument,
    item.contract,
    item.entry_time,
    item.exit_time || "Open",
    item.side,
    item.quantity,
    item.entry_price,
    item.exit_price || "",
    item.exit_reason,
    item.gross_pnl,
    item.net_pnl,
    item.evidence_quality,
    item.explanation_completeness,
  ]);
  renderTable("historicalTradesTable", rows);
}

function renderAlerts() {
  const alerts = state.projection?.alerts || [];
  const target = document.getElementById("alertsPanel");
  document.getElementById("alertsSummary").innerHTML = [
    badgeMarkup("bad", `${alerts.filter(item => item.severity === "CRITICAL").length} critical`),
    badgeMarkup("warn", `${alerts.filter(item => item.severity === "WARNING").length} warning`),
    badgeMarkup("neutral", `${alerts.length} total`),
  ].join("");
  target.innerHTML = "";
  if (!alerts.length) {
    target.appendChild(panel("No Active Alerts", { Status: "CLEAR", Meaning: "The snapshot does not contain active alert records." }));
    return;
  }
  alerts.forEach(alert => {
    target.appendChild(panel(alert.code || "Alert", alert));
  });
}

function renderAudit() {
  const auditRows = state.projection?.audit || [];
  document.getElementById("auditSummary").innerHTML = [
    badgeMarkup("neutral", `${auditRows.length} audit event(s)`),
    badgeMarkup("neutral", "Technical details available in table"),
  ].join("");
  renderTable("auditTable", (state.projection?.audit || []).map(a => [a.operator, a.timestamp, a.command, a.scope, a.reason, String(a.preview), a.result, a.previous_state, a.new_state, a.evidence_hash]));
}

function renderDiagnostics() {
  const selected = getSelectedStrategy();
  const panelTarget = document.getElementById("diagnosticsPanel");
  panelTarget.innerHTML = "";
  panelTarget.appendChild(panel("System", {
    Session: state.projection?.system?.session,
    "Projection version": state.projection?.system?.projection_version,
    "Broker order authority": state.projection?.system?.broker_order_authority,
    Runtime: state.projection?.system?.runtime,
  }));
  if (selected) {
    panelTarget.appendChild(panel(`${selected.identity.strategy} ${selected.identity.instrument}`, {
      "Strategy Instance ID": selected.identity.instance,
      "Read model hash": selected.read_model_hash,
      "Plan hash": selected.plan.plan_hash,
      "Evidence quality": selected.state.evidence_quality,
      "Latest event": selected.execution.latest_event,
    }));
  }
  document.getElementById("diagnosticsBlock").textContent = JSON.stringify({
    system: state.projection?.system,
    navigation: state.projection?.navigation,
    selected_strategy: selected ? selected.identity.instance : null,
    projection_hash: state.projection?.projection_hash,
  }, null, 2);
}

function renderSourceTraceWorkspace() {
  const selected = getSelectedStrategy();
  const target = document.getElementById("sourceTracePanel");
  if (!selected) {
    target.innerHTML = renderWarningBox("Select one strategy to inspect source trace.");
    return;
  }
  target.innerHTML = renderSourceTrace(selected, getFactsForStrategy(selected.identity.instance));
}

function renderSettings() {
  const projection = state.projection;
  document.getElementById("settingsSummary").innerHTML = renderKeyValuePairs({
    Session: projection.system?.session,
    "Broker order authority": projection.system?.broker_order_authority,
    "Projection hash": projection.projection_hash,
    "Decision facts": (projection.decision_explanations || []).length,
    "Strategy rows": (projection.strategies || []).length,
  });
  document.getElementById("settingsBlock").textContent = JSON.stringify({
    system: projection.system,
    projection_hash: projection.projection_hash,
    command_centre: projection.command_centre,
  }, null, 2);
}

function renderMetricCards(id, payload) {
  const target = document.getElementById(id);
  const priorityKeys = [
    "active_orders",
    "blocked_instances",
    "broker_sessions",
    "critical_alerts",
    "enabled_strategy_instances",
    "market_state",
    "open_positions",
    "plans_prepared",
    "realized_pnl",
    "system_state",
    "unprotected_positions",
  ];
  const hiddenKeys = new Set([
    "critical_alert_rows",
    "recent_operational_events",
    "strategy_health",
    "pending_actions",
    "active_trades",
    "market_session_timeline",
    "account_summary",
    "strategy_definition_summaries",
  ]);
  const entries = Object.entries(payload || {})
    .filter(([key]) => !hiddenKeys.has(key))
    .sort((a, b) => {
      const left = priorityKeys.indexOf(a[0]);
      const right = priorityKeys.indexOf(b[0]);
      return (left === -1 ? 999 : left) - (right === -1 ? 999 : right);
    })
    .slice(0, 10);
  target.innerHTML = entries.map(([key, value]) => `
    <article class="metric">
      <span>${escapeHtml(label(key))}</span>
      <strong>${escapeHtml(display(value))}</strong>
    </article>
  `).join("");
}

function renderTable(id, rows, options = {}) {
  const table = document.getElementById(id);
  const multiline = Boolean(options.multiline);
  const headers = columns[id] || [];
  const head = headers.map((name, index) => `<th data-index="${index}">${escapeHtml(name)}</th>`).join("");
  const body = (rows || []).map(row => `<tr>${row.map(cell => `<td>${formatCell(cell, multiline)}</td>`).join("")}</tr>`).join("");
  table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
  table.classList.toggle("table-compact", id !== "explainabilityTable");
  table.querySelectorAll("th").forEach(th => {
    th.addEventListener("click", () => sortTable(id, Number(th.dataset.index)));
  });
}

function populateStrategyFilterControls() {
  const options = state.projection?.strategy_filter_options || {};
  populateSelect("strategyStatusFilter", [{ value: "all", label: "All stages" }].concat((options.stages || []).map(item => ({ value: item, label: display(item) }))));
  populateSelect("strategyMonthlyFilter", [{ value: "all", label: "All monthly states" }].concat((options.monthly_statuses || []).map(item => ({ value: item, label: display(item) }))));
  populateSelect("strategyBranchFilter", [{ value: "all", label: "All branches" }].concat((options.branches || []).map(item => ({ value: item, label: display(item) }))));
  populateSelect("strategyHealthFilter", [{ value: "all", label: "All health" }].concat((options.health || []).map(item => ({ value: item, label: display(item) }))));
  populateSelect("strategyEvidenceFilter", [{ value: "all", label: "All evidence" }].concat((options.evidence || []).map(item => ({ value: item, label: display(item) }))));
  populateSelect("strategyAccountFilter", [{ value: "all", label: "All accounts" }].concat((options.accounts || []).map(item => ({ value: item, label: item }))));
  populateSelect("strategyEnabledFilter", [
    { value: "all", label: "Enabled + disabled" },
    { value: "enabled", label: "Enabled only" },
    { value: "disabled", label: "Disabled only" },
  ]);
  populateSelect("strategySortKey", (options.sort_fields || []).map(item => ({ value: item.key, label: item.label })));
  populateSelect("strategyPageSize", (options.page_sizes || [10]).map(item => ({ value: String(item), label: `${item} per page` })));
  populateSelect("strategySavedViews", [{ value: "", label: "Saved views" }].concat(loadSavedStrategyViews().map(item => ({ value: item.name, label: item.name }))));

  document.getElementById("strategyStatusFilter").value = state.strategyView.filters.status;
  document.getElementById("strategyMonthlyFilter").value = state.strategyView.filters.monthly;
  document.getElementById("strategyBranchFilter").value = state.strategyView.filters.branch;
  document.getElementById("strategyHealthFilter").value = state.strategyView.filters.health;
  document.getElementById("strategyEvidenceFilter").value = state.strategyView.filters.evidence;
  document.getElementById("strategyAccountFilter").value = state.strategyView.filters.account;
  document.getElementById("strategyEnabledFilter").value = state.strategyView.filters.enabled;
  document.getElementById("strategySortKey").value = state.strategyView.sortKey;
  document.getElementById("strategyPageSize").value = String(state.strategyView.pageSize);
  document.getElementById("strategyDensityToggle").textContent = `Density: ${state.strategyView.density === "compact" ? "Compact" : "Detailed"}`;
  document.getElementById("strategySortDirection").textContent = state.strategyView.sortDir === "asc" ? "Asc" : "Desc";
}

function populateSelect(id, rows) {
  const target = document.getElementById(id);
  if (!target) return;
  target.innerHTML = (rows || []).map(item => `<option value="${escapeHtml(String(item.value))}">${escapeHtml(String(item.label))}</option>`).join("");
}

function buildOptionRows(rows, valueKey, labelKey) {
  return (rows || []).map(item => ({ value: item[valueKey], label: item[labelKey] }));
}

function onStrategyFilterChange() {
  state.strategyView.filters.status = document.getElementById("strategyStatusFilter").value;
  state.strategyView.filters.monthly = document.getElementById("strategyMonthlyFilter").value;
  state.strategyView.filters.branch = document.getElementById("strategyBranchFilter").value;
  state.strategyView.filters.health = document.getElementById("strategyHealthFilter").value;
  state.strategyView.filters.evidence = document.getElementById("strategyEvidenceFilter").value;
  state.strategyView.filters.account = document.getElementById("strategyAccountFilter").value;
  state.strategyView.filters.enabled = document.getElementById("strategyEnabledFilter").value;
  state.strategyView.page = 1;
  renderWorkbench();
}

function onStrategySortChange() {
  state.strategyView.sortKey = document.getElementById("strategySortKey").value;
  renderWorkbench();
}

function toggleStrategySortDirection() {
  state.strategyView.sortDir = state.strategyView.sortDir === "asc" ? "desc" : "asc";
  renderWorkbench();
}

function onStrategyPageSizeChange() {
  state.strategyView.pageSize = Number(document.getElementById("strategyPageSize").value) || 10;
  state.strategyView.page = 1;
  renderWorkbench();
}

function toggleStrategyDensity() {
  state.strategyView.density = state.strategyView.density === "compact" ? "detailed" : "compact";
  renderWorkbench();
}

function saveStrategyView() {
  const name = window.prompt("Save this strategy view as:");
  if (!name) return;
  const views = loadSavedStrategyViews().filter(item => item.name !== name);
  views.push({ name, state: state.strategyView });
  localStorage.setItem("tfis.strategyViews", JSON.stringify(views));
  populateStrategyFilterControls();
}

function loadSavedStrategyViews() {
  try {
    return JSON.parse(localStorage.getItem("tfis.strategyViews") || "[]");
  } catch {
    return [];
  }
}

function applySavedStrategyView() {
  const name = document.getElementById("strategySavedViews").value;
  const selected = loadSavedStrategyViews().find(item => item.name === name);
  if (!selected) return;
  state.strategyView = JSON.parse(JSON.stringify(selected.state));
  document.getElementById("strategyFilter").value = state.strategyView.search || "";
  populateStrategyFilterControls();
  renderWorkbench();
}

function exportStrategyView() {
  const filtered = getFilteredStrategyRows({ ignorePaging: true });
  const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "tfis_strategy_view.json";
  link.click();
  URL.revokeObjectURL(url);
}

function selectAdjacentStrategy(offset) {
  const filtered = getInstancesForCurrentDefinition();
  const index = filtered.findIndex(item => item.strategy_instance_id === state.selectedStrategyId);
  const next = filtered[index + offset];
  if (!next) return;
  state.selectedStrategyId = next.strategy_instance_id;
  state.activeTab = "decision-workbench";
  syncRouteState();
  render();
}

function sortTable(id, index) {
  const rows = Array.from(document.querySelectorAll(`#${id} tbody tr`));
  const current = state.sort[id];
  const asc = !(current && current.index === index && current.asc);
  state.sort[id] = { index, asc };
  rows.sort((a, b) => a.children[index].textContent.localeCompare(b.children[index].textContent, undefined, { numeric: true }) * (asc ? 1 : -1));
  const body = document.querySelector(`#${id} tbody`);
  rows.forEach(row => body.appendChild(row));
}

function updateVisibleWorkspace() {
  document.querySelectorAll(".workspace-tab").forEach(section => {
    section.style.display = section.id === `tab-${resolveWorkspaceTabKey(state.activeTab)}` ? "" : "none";
  });
}

function renderStrategyFamilies() {
  const target = document.getElementById("strategyFamilyGrid");
  const families = state.projection?.strategy_families || [];
  target.innerHTML = families.map(item => `
    <article class="strategy-card">
      <div class="card-head">
        <div>
          <p class="section-kicker">${escapeHtml(item.family)}</p>
          <h3>${escapeHtml(String(item.instrument_count || 0))} instrument instance(s)</h3>
        </div>
        ${badgeMarkup(item.scalability_demo ? "accent" : "neutral", item.health || "Not enabled")}
      </div>
      <div class="card-grid">
        ${infoCell("Strategies", item.strategy_count)}
        ${infoCell("Active positions", item.active_positions)}
        ${infoCell("Blocked", item.blocked)}
        ${infoCell("No trade", item.no_trade)}
        ${infoCell("Daily P&L", item.daily_pnl)}
        ${infoCell("Evidence", item.evidence_quality)}
      </div>
    </article>
  `).join("");
}

function renderStrategyDefinitionTable(definitions) {
  const rows = (definitions || []).map(item => [
    `<button type="button" class="table-action-link" data-definition-select="${escapeHtml(item.strategy_definition_id)}">${escapeHtml(item.strategy_code)} - ${escapeHtml(item.display_name)}</button>`,
    item.family,
    item.segment,
    item.supported_count,
    item.enabled_count,
    item.prepared_count,
    item.qualified_count,
    item.entry_available_count,
    item.open_count,
    item.carried_count,
    item.blocked_count,
    item.no_trade_count,
    item.realized_pnl,
    item.unrealized_pnl,
    `${display(item.margin_usage_pct)}%`,
    item.health,
    item.evidence_quality,
    item.last_update,
  ]);
  renderTable("strategyDefinitionsTable", rows);
  document.querySelectorAll("[data-definition-select]").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedDefinitionId = button.dataset.definitionSelect;
      state.strategyView.page = 1;
      state.selectedStrategyId = null;
      state.activeTab = "opportunity-queue";
      syncRouteState();
      render();
    });
  });
}

function renderStrategyQuickViews(quickViews) {
  const target = document.getElementById("strategyQuickViews");
  target.innerHTML = (quickViews || []).map(item => `
    <button type="button" class="quick-view-chip ${state.strategyView.quickView === item.key ? "is-active" : ""}" data-quick-view="${escapeHtml(item.key)}">
      ${escapeHtml(item.label)} (${escapeHtml(String(item.count))})
    </button>
  `).join("");
  target.querySelectorAll("[data-quick-view]").forEach(button => {
    button.addEventListener("click", () => {
      state.strategyView.quickView = button.dataset.quickView;
      state.strategyView.page = 1;
      renderWorkbench();
    });
  });
}

function renderStrategyInstanceList(selectedDefinition, filtered, paged) {
  document.getElementById("strategyInstanceListTitle").textContent = selectedDefinition
    ? `${selectedDefinition.strategy_code} instance list`
    : "Select a strategy definition";
  document.getElementById("strategyInstanceSummary").innerHTML = [
    badgeMarkup("neutral", `${filtered.length} row(s) after filters`),
    badgeMarkup("good", `${filtered.filter(item => item.position === "OPEN_PROTECTED").length} open protected`),
    badgeMarkup("warn", `${filtered.filter(item => item.has_alerts).length} with alerts`),
    badgeMarkup("neutral", `${state.strategyView.pageSize} per page`),
  ].join("");
  const rows = paged.map(item => [
    item.instrument,
    item.enabled_label,
    item.account_display_name || item.account,
    item.monthly_status,
    item.branch,
    item.current_stage,
    item.selected_contract,
    item.entry,
    item.position_label,
    item.realized_pnl,
    item.unrealized_pnl,
    item.health_label,
    item.evidence_label,
    item.last_update,
    `<button type="button" class="action-button table-button" data-strategy-select="${escapeHtml(item.strategy_instance_id)}">Open</button>`,
  ]);
  renderTable("strategyInstancesTable", rows);
  document.getElementById("strategyInstancesTable").classList.toggle("table-detailed", state.strategyView.density === "detailed");
  document.querySelectorAll("[data-strategy-select]").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedStrategyId = button.dataset.strategySelect;
      const selectedRow = filtered.find(item => item.strategy_instance_id === button.dataset.strategySelect);
      if (selectedRow?.strategy_definition_id) {
        state.selectedDefinitionId = selectedRow.strategy_definition_id;
      }
      state.activeTab = "decision-workbench";
      state.explainTab = "overview";
      syncRouteState();
      render();
    });
  });
  renderStrategyPagination(filtered.length);
}

function renderStrategyPagination(totalCount) {
  const pageCount = Math.max(1, Math.ceil(totalCount / state.strategyView.pageSize));
  state.strategyView.page = Math.min(state.strategyView.page, pageCount);
  const target = document.getElementById("strategyPagination");
  target.innerHTML = `
    <button type="button" class="action-button" data-page-nav="prev">Previous</button>
    <span class="pagination-status">Page ${escapeHtml(String(state.strategyView.page))} of ${escapeHtml(String(pageCount))}</span>
    <button type="button" class="action-button" data-page-nav="next">Next</button>
  `;
  target.querySelectorAll("[data-page-nav]").forEach(button => {
    button.addEventListener("click", () => {
      if (button.dataset.pageNav === "prev" && state.strategyView.page > 1) state.strategyView.page -= 1;
      if (button.dataset.pageNav === "next" && state.strategyView.page < pageCount) state.strategyView.page += 1;
      renderWorkbench();
    });
  });
}

function getSelectedDefinition() {
  return (state.projection?.strategy_definitions || []).find(item => item.strategy_definition_id === state.selectedDefinitionId) || null;
}

function getInstancesForCurrentDefinition() {
  return (state.projection?.strategy_instances || [])
    .filter(item => !state.selectedDefinitionId || item.strategy_definition_id === state.selectedDefinitionId)
    .sort((left, right) => String(left.instrument || "").localeCompare(String(right.instrument || ""), undefined, { numeric: true }));
}

function getQuickViewsForSelectedDefinition() {
  const selectedDefinition = getSelectedDefinition();
  const counts = selectedDefinition
    ? (state.projection?.strategy_status_counts?.by_definition?.[selectedDefinition.strategy_definition_id] || {})
    : (state.projection?.strategy_status_counts?.global || {});
  return [
    { key: "all", label: "All", count: counts.all || 0 },
    { key: "enabled", label: "Enabled", count: counts.enabled || 0 },
    { key: "entry_available", label: "Entry Available", count: counts.entry_available || 0 },
    { key: "open_positions", label: "Open Positions", count: counts.open_positions || 0 },
    { key: "carried", label: "Carried", count: counts.carried || 0 },
    { key: "blocked", label: "Blocked", count: counts.blocked || 0 },
    { key: "no_trade", label: "No Trade", count: counts.no_trade || 0 },
    { key: "missing_evidence", label: "Missing Evidence", count: counts.missing_evidence || 0 },
    { key: "alerts", label: "Alerts", count: counts.alerts || 0 },
  ];
}

function getFilteredStrategyRows(options = {}) {
  const ignorePaging = Boolean(options.ignorePaging);
  const rows = getInstancesForCurrentDefinition();
  state.strategyView.search = document.getElementById("strategyFilter").value.trim().toLowerCase();
  let filtered = rows.filter(item => !state.strategyView.search || JSON.stringify(item).toLowerCase().includes(state.strategyView.search));
  filtered = filtered.filter(item => matchesQuickView(item, state.strategyView.quickView));
  filtered = filtered.filter(item => state.strategyView.filters.status === "all" || String(item.current_stage) === state.strategyView.filters.status);
  filtered = filtered.filter(item => state.strategyView.filters.monthly === "all" || String(item.monthly_status) === state.strategyView.filters.monthly);
  filtered = filtered.filter(item => state.strategyView.filters.branch === "all" || String(item.branch) === state.strategyView.filters.branch);
  filtered = filtered.filter(item => state.strategyView.filters.health === "all" || String(item.health) === state.strategyView.filters.health);
  filtered = filtered.filter(item => state.strategyView.filters.evidence === "all" || String(item.evidence) === state.strategyView.filters.evidence);
  filtered = filtered.filter(item => state.strategyView.filters.account === "all" || String(item.account_display_name || item.account) === state.strategyView.filters.account);
  filtered = filtered.filter(item => state.strategyView.filters.enabled === "all" || String(item.enabled) === (state.strategyView.filters.enabled === "enabled" ? "true" : "false"));
  filtered.sort((a, b) => compareStrategyRows(a, b, state.strategyView.sortKey, state.strategyView.sortDir));
  return ignorePaging ? filtered : filtered;
}

function renderDefinitionSummaryChips(definition, instances) {
  if (!definition) {
    return "";
  }
  const openCount = instances.filter(item => String(item.position || "").startsWith("OPEN")).length;
  const readyCount = instances.filter(item => Boolean(item.entry_available)).length;
  const blockedCount = instances.filter(item => Boolean(item.blocked)).length;
  return [
    badgeMarkup("neutral", `${definition.strategy_code} ${display(definition.display_name || "")}`.trim()),
    badgeMarkup("neutral", `${instances.length} instrument(s)`),
    badgeMarkup("good", `${readyCount} ready`),
    badgeMarkup("neutral", `${openCount} open`),
    badgeMarkup(blockedCount ? "warn" : "neutral", `${blockedCount} blocked`),
  ].join("");
}

function renderInstanceNavigator(instances, selectedInstanceId) {
  if (!(instances || []).length) {
    return `<div class="empty-inline">No instrument instances are available for this strategy definition.</div>`;
  }
  return `
    <div class="instance-switcher-head">
      <strong>Jump to instrument</strong>
      <span>${escapeHtml(String(instances.length))} instance(s)</span>
    </div>
    <div class="instance-switcher-grid">
      ${instances.map(item => `
        <button
          type="button"
          class="instance-switch-card ${item.strategy_instance_id === selectedInstanceId ? "is-selected" : ""}"
          data-instance-switch="${escapeHtml(item.strategy_instance_id)}"
        >
          <span class="instance-switch-topline">
            <strong>${escapeHtml(display(item.instrument))}</strong>
            ${badgeMarkup(item.health === "HEALTHY" ? "good" : getHealthTone(item.health), item.health_label || item.health || "Unknown")}
          </span>
          <span class="instance-switch-meta">${escapeHtml(display(item.monthly_status))} · ${escapeHtml(display(item.branch))}</span>
          <span class="instance-switch-meta">${escapeHtml(display(item.current_stage))}</span>
          <span class="instance-switch-meta">Entry ${escapeHtml(display(item.entry))} · Contract ${escapeHtml(display(item.selected_contract || "Pending"))}</span>
        </button>
      `).join("")}
    </div>
  `;
}

function getPagedStrategyRows(filtered) {
  const start = (state.strategyView.page - 1) * state.strategyView.pageSize;
  return filtered.slice(start, start + state.strategyView.pageSize);
}

function compareStrategyRows(a, b, key, direction) {
  const left = a[key];
  const right = b[key];
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  let result;
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    result = leftNumber - rightNumber;
  } else {
    result = String(left ?? "").localeCompare(String(right ?? ""), undefined, { numeric: true });
  }
  return direction === "asc" ? result : -result;
}

function matchesQuickView(item, quickView) {
  if (quickView === "all") return true;
  if (quickView === "enabled") return Boolean(item.enabled);
  if (quickView === "entry_available") return Boolean(item.entry_available);
  if (quickView === "open_positions") return String(item.position).startsWith("OPEN");
  if (quickView === "carried") return item.fresh_or_carried === "CARRIED";
  if (quickView === "blocked") return Boolean(item.blocked);
  if (quickView === "no_trade") return Boolean(item.no_trade);
  if (quickView === "missing_evidence") return ["DEGRADED_EVIDENCE", "DETERMINISTIC_TIMING_SUPPLEMENT"].includes(String(item.evidence));
  if (quickView === "alerts") return Boolean(item.has_alerts);
  return true;
}

function getSelectedStrategy() {
  return (state.projection?.strategies || []).find(item => item.identity.instance === state.selectedStrategyId) || null;
}

function getFactsForStrategy(strategyInstanceId) {
  return (state.projection?.decision_explanations || []).filter(item => item.strategy_instance_id === strategyInstanceId);
}

function summaryRow(labelText, value) {
  return `<div class="summary-row"><span>${escapeHtml(labelText)}</span><strong>${escapeHtml(value)}</strong></div>`;
}

function summaryTile(labelText, value) {
  return `
    <div class="summary-tile">
      <span>${escapeHtml(labelText)}</span>
      <strong>${escapeHtml(display(value))}</strong>
    </div>
  `;
}

function renderKeyFactsPanel(values, title) {
  return `
    <div class="detail-block">
      <h4>${escapeHtml(title)}</h4>
      <div class="key-value-grid">
        ${renderKeyValuePairs(values)}
      </div>
    </div>
  `;
}

function renderKeyValuePairs(values) {
  return Object.entries(values || {}).map(([key, value]) => `
    <div class="kv-row">
      <span>${escapeHtml(label(key))}</span>
      <strong>${escapeHtml(display(value))}</strong>
    </div>
  `).join("");
}

function checklistItem(item) {
  return `
    <article class="check-item tone-${item.tone}">
      <div class="check-head">
        <strong>${escapeHtml(item.label)}</strong>
        ${badgeMarkup(item.tone, item.status)}
      </div>
      <p>${escapeHtml(item.copy)}</p>
    </article>
  `;
}

function renderSimpleTable(headers, rows, emptyMessage) {
  if (!(rows || []).length) {
    return `<div class="empty-inline">${escapeHtml(emptyMessage)}</div>`;
  }
  return `
    <div class="mini-table-wrap">
      <table class="mini-table">
        <thead><tr>${headers.map(item => `<th>${escapeHtml(item)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${isTrustedMarkup(cell) ? cell : escapeHtml(display(cell))}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
  `;
}

function metricTile(labelText, value) {
  return `
    <div class="summary-tile">
      <span>${escapeHtml(labelText)}</span>
      <strong>${escapeHtml(display(value))}</strong>
    </div>
  `;
}

function infoCell(labelText, value) {
  return `
    <div class="info-cell">
      <span>${escapeHtml(labelText)}</span>
      <strong>${escapeHtml(display(value))}</strong>
    </div>
  `;
}

function panel(title, data) {
  const item = document.createElement("article");
  item.className = "panel";
  item.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <div class="key-value-grid">${renderKeyValuePairs(data)}</div>
  `;
  return item;
}

function badgeMarkup(tone, text) {
  return `<span class="badge ${badgeClass(tone)}">${escapeHtml(text)}</span>`;
}

function badgeClass(tone) {
  return {
    good: "badge-good",
    warn: "badge-warn",
    bad: "badge-bad",
    accent: "badge-accent",
    neutral: "badge-neutral",
  }[tone] || "badge-neutral";
}

function getHealthTone(value) {
  const text = String(value || "").toUpperCase();
  if (text.includes("HEALTHY") || text.includes("PROTECTED") || text.includes("PASS")) return "good";
  if (text.includes("WARN") || text.includes("PENDING") || text.includes("LIMITED") || text.includes("DEGRADED")) return "warn";
  if (text.includes("BLOCK") || text.includes("FAIL") || text.includes("MISS")) return "bad";
  return "neutral";
}

function renderMatchBadge(engineValue, manualValue) {
  if (!manualValue) {
    return badgeMarkup("neutral", "Pending");
  }
  return badgeMarkup(normalizeComparable(engineValue) === normalizeComparable(manualValue) ? "good" : "warn", normalizeComparable(engineValue) === normalizeComparable(manualValue) ? "Match" : "Diff");
}

function computeManualDifference(engineValue, manualValue) {
  if (!manualValue) return "";
  const engineNumber = Number(engineValue);
  const manualNumber = Number(manualValue);
  if (Number.isFinite(engineNumber) && Number.isFinite(manualNumber)) {
    return String((manualNumber - engineNumber).toFixed(4));
  }
  return normalizeComparable(engineValue) === normalizeComparable(manualValue) ? "0" : "n/a";
}

function normalizeComparable(value) {
  return String(value ?? "").trim();
}

function renderWarningBox(text) {
  return `<div class="warning-box">${escapeHtml(text)}</div>`;
}

function buildOperatorChecklist(strategy) {
  const completeness = getStrategyCompleteness(strategy);
  const selectedContractReady = strategy.plan.selected_contract ? "good" : "bad";
  const entryReady = strategy.plan.base_entry ? "good" : "bad";
  const protectionReady = strategy.plan.target && strategy.plan.original_sl ? "good" : "bad";
  return [
    {
      label: "Monthly Status and branch",
      status: strategy.state.monthly_status && strategy.state.branch ? "Visible" : "Missing",
      tone: strategy.state.monthly_status && strategy.state.branch ? "good" : "bad",
      copy: "Confirm the backend returned a Monthly Status and mapped it to the expected strategy branch.",
    },
    {
      label: "Contract selection",
      status: strategy.plan.selected_contract ? "Selected" : "Missing",
      tone: selectedContractReady,
      copy: "Validate expiry, option side, strike, premium, and OI before trusting the trade path.",
    },
    {
      label: "Entry and timing",
      status: strategy.plan.base_entry ? "Visible" : "Missing",
      tone: entryReady,
      copy: "Check Base Entry together with ORPT and RC state before looking at order state.",
    },
    {
      label: "Target and stop-loss",
      status: strategy.plan.target && strategy.plan.original_sl ? "Visible" : "Missing",
      tone: protectionReady,
      copy: "Confirm the protection numbers shown by the backend before position review.",
    },
    {
      label: "Explainability completeness",
      status: completeness.label,
      tone: completeness.badgeTone,
      copy: "Use this as the honesty meter for how much of the decision is fact-backed in the current snapshot.",
    },
  ];
}

function renderDecisionContextStrip(strategy) {
  return `
    <div class="context-strip">
      ${summaryTile("Strategy", strategy.identity.strategy)}
      ${summaryTile("Instrument", strategy.identity.instrument)}
      ${summaryTile("Account", strategy.identity.account_display_name || strategy.identity.account)}
      ${summaryTile("Session", strategy.identity.session)}
    </div>
  `;
}

function renderDecisionChecklistCompact(strategy) {
  const completeness = getStrategyCompleteness(strategy);
  return `
    <div class="compact-checklist">
      ${badgeMarkup(strategy.state.monthly_status && strategy.state.branch ? "good" : "bad", `Monthly ${strategy.state.monthly_status && strategy.state.branch ? "ready" : "missing"}`)}
      ${badgeMarkup(strategy.plan.selected_contract ? "good" : "bad", `Contract ${strategy.plan.selected_contract ? "selected" : "missing"}`)}
      ${badgeMarkup(strategy.plan.base_entry ? "good" : "bad", `Entry ${strategy.plan.base_entry ? "visible" : "missing"}`)}
      ${badgeMarkup(strategy.plan.target && strategy.plan.original_sl ? "good" : "bad", `Protection ${strategy.plan.target && strategy.plan.original_sl ? "visible" : "missing"}`)}
      ${badgeMarkup(completeness.badgeTone, `Explainability ${completeness.label}`)}
    </div>
  `;
}

function isTrustedMarkup(value) {
  if (typeof value !== "string") {
    return false;
  }
  return value.includes("<input") || value.includes('class="badge') || value.includes("<button");
}

function formatCell(cell, multiline) {
  if (cell === null || cell === undefined) {
    return "";
  }
  const raw = String(cell);
  if (isTrustedMarkup(raw)) {
    return raw;
  }
  return multiline ? escapeHtml(display(cell)).replaceAll(" | ", "<br>") : escapeHtml(display(cell));
}

function inferOptionChoice(branch) {
  const value = String(branch || "").toUpperCase();
  if (value.includes("CALL")) return "CALL";
  if (value.includes("PUT")) return "PUT";
  return "";
}

function inferDirectionalChoice(branch) {
  const value = String(branch || "").toUpperCase();
  if (value.includes("BULL")) return "BULL";
  if (value.includes("BEAR")) return "BEAR";
  return "";
}

function buildBranchNarrative(branch) {
  const option = inferOptionChoice(branch);
  const direction = inferDirectionalChoice(branch);
  if (!branch) return "";
  return `${direction || "Unknown"} market branch resolved to ${option || "unknown option side"} handling for this strategy instance.`;
}

function explainMonthlyStatus(status) {
  const value = String(status || "").toUpperCase();
  if (value === "BULL") return "The monthly market view is bullish, but not yet in the confirmed bullish continuation state.";
  if (value === "BULL_CF") return "The monthly market view is bullish and also in the confirmed bullish continuation state.";
  if (value === "BEAR") return "The monthly market view is bearish, but not yet in the confirmed bearish continuation state.";
  if (value === "BEAR_CF") return "The monthly market view is bearish and also in the confirmed bearish continuation state.";
  return "Monthly market bias is unavailable or not yet explained in operator language.";
}

function monthlyStatusReadingGuide(status) {
  const value = String(status || "").toUpperCase();
  if (value.startsWith("BULL")) return "Read this as: TFIS sees the higher-timeframe market bias as bullish before choosing the strategy branch.";
  if (value.startsWith("BEAR")) return "Read this as: TFIS sees the higher-timeframe market bias as bearish before choosing the strategy branch.";
  return "Monthly Status is missing, so the branch should be treated carefully until the upstream market-bias result is available.";
}

function explainMonthlyReference(referenceKey) {
  const key = String(referenceKey || "").toUpperCase();
  if (key === "PMH") return "Previous month high";
  if (key === "PML") return "Previous month low";
  if (key === "CMH") return "Current month high so far";
  if (key === "CML") return "Current month low so far";
  if (key === "PWH") return "Previous week high";
  if (key === "PWL") return "Previous week low";
  if (key === "CWH") return "Current week high so far";
  if (key === "CWL") return "Current week low so far";
  if (key === "CURRENT_PRICE") return "Current price used when the monthly engine applies transition or continuation rules";
  return "Monthly engine reference value";
}

function explainEntryState(stateValue) {
  const text = String(stateValue || "").toUpperCase();
  if (text.includes("RC")) return "The normal path did not finish cleanly and the RC state is governing current eligibility.";
  if (text.includes("VALID")) return "The entry path is still treated as eligible in the current projection.";
  if (text.includes("OPEN")) return "The strategy has already progressed beyond pre-entry review into position state.";
  if (text.includes("BLOCK")) return "The strategy is blocked and should not be treated as entry-ready.";
  return "Review this state together with ORPT, RC, and the latest event before acting on it.";
}

function display(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (Array.isArray(value)) return value.map(item => display(item)).join(", ");
  if (typeof value === "object") return summarizeObject(value);
  return formatDisplayString(String(value));
}

function formatDisplayString(raw) {
  if (!raw) return "";
  if (VALUE_LABELS[raw]) {
    return VALUE_LABELS[raw];
  }
  if (/^\d{2}:\d{2}:\d{2}\.\d+$/.test(raw)) {
    return formatClockValue(raw);
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/.test(raw)) {
    return formatIsoDateTime(raw);
  }
  if (/^[A-Z0-9]+(?:_[A-Z0-9]+)+$/.test(raw)) {
    return raw
      .split("_")
      .map(token => token.charAt(0) + token.slice(1).toLowerCase())
      .join(" ");
  }
  return raw;
}

function formatClockValue(raw) {
  const match = raw.match(/^(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?$/);
  if (!match) return raw;
  let hour = Number(match[1]);
  const minutes = match[2];
  const seconds = match[3];
  const micros = match[4] || "";
  const suffix = hour >= 12 ? "PM" : "AM";
  hour = hour % 12 || 12;
  const trimmed = micros.replace(/0+$/, "");
  const milli = trimmed ? `.${trimmed.slice(0, 3)}` : "";
  return `${String(hour).padStart(2, "0")}:${minutes}:${seconds}${milli} ${suffix}`;
}

function shortenHash(value) {
  const raw = String(value || "");
  if (raw.length <= 16) return raw;
  return `${raw.slice(0, 8)}...${raw.slice(-6)}`;
}

function formatIsoDateTime(raw) {
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2}:\d{2})(?:\.(\d+))?([+-]\d{2}:\d{2}|Z)?$/);
  if (!match) return raw;
  const datePart = `${match[1]}-${match[2]}-${match[3]}`;
  const timePart = formatClockValue(`${match[4]}${match[5] ? `.${match[5]}` : ""}`);
  const zone = match[6] === "+05:30" ? "IST" : (match[6] || "");
  return [datePart, timePart, zone].filter(Boolean).join(" ");
}

function summarizeObject(value) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) {
    return value.map(item => typeof item === "object" ? JSON.stringify(item) : String(item)).join(" | ");
  }
  return Object.entries(value).map(([key, item]) => `${label(key)}: ${display(item)}`).join(" | ");
}

function label(key) {
  if (KEY_LABELS[key]) {
    return KEY_LABELS[key];
  }
  return String(key).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toggleTheme() {
  document.body.classList.toggle("dark");
}

init();
