const OPERATOR_TABS = [
  { key: "command-centre", label: "Command Centre", description: "Critical operating health, actions, and session state." },
  { key: "strategies", label: "Strategies", description: "Family hierarchy plus strategy-instance workbench." },
  { key: "orders", label: "Orders", description: "Operator-facing order list with warnings and technical details." },
  { key: "positions", label: "Positions", description: "Protected exposure, lifecycle, and P&L state." },
  { key: "accounts", label: "Accounts", description: "Account summary and internal-paper configuration controls." },
  { key: "risk", label: "Risk", description: "Margin, exposure, warnings, and capacity monitoring." },
  { key: "historical-trades", label: "Historical Trades", description: "Trade stories and explanation completeness." },
  { key: "alerts", label: "Alerts", description: "Warnings, health signals, and operator attention items." },
  { key: "audit", label: "Audit", description: "Configuration and runtime history for controlled review." },
  { key: "settings", label: "Settings", description: "Projection metadata and raw snapshot." },
];

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
  ["1. Pick strategy", "Open one strategy from the left rail or workbench."],
  ["2. Validate branch", "Confirm Monthly Status and branch before looking at trade prices."],
  ["3. Validate contract", "Check expiry, strike, premium, OI, and rejected candidates."],
  ["4. Validate timing", "Review ORPT, RC, and current eligibility state."],
  ["5. Validate protection", "Check Target, SL, quantity, and current position health."],
  ["6. Compare manually", "Use Manual Comparison to contrast your own numbers with the engine."],
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

const state = {
  projection: null,
  mode: "operator",
  activeTab: "command-centre",
  selectedStrategyId: null,
  explainTab: "overview",
  manualInputs: {},
  sort: {},
};

const columns = {
  ordersTable: ["Account", "Strategy", "Instance", "PositionCycle", "Instrument", "Contract", "Purpose", "Generation", "Requested", "Filled", "Price", "State", "Age", "Latest Event", "Failure"],
  positionsTable: ["Account", "Strategy", "Instrument", "Contract", "Fresh/Carried", "Quantity", "Average Entry", "Mark", "Target", "Active SL", "Protection", "Realized", "Unrealized", "Exit Deadline", "Health"],
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
  document.getElementById("explainabilityFilter").addEventListener("input", renderExplainabilityLibrary);
  document.getElementById("engineeringExplainabilityFilter").addEventListener("input", renderEngineeringExplainabilityLibrary);
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
  state.projection = await response.json();
  ensureSelectedStrategy();
  render();
}

function ensureSelectedStrategy() {
  const strategies = state.projection?.strategies || [];
  if (!strategies.length) {
    state.selectedStrategyId = null;
    return;
  }
  if (!strategies.some(item => item.identity.instance === state.selectedStrategyId)) {
    state.selectedStrategyId = strategies[0].identity.instance;
  }
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
  return `${display(centre.enabled_strategy_instances)} strategy instances, ${display(centre.open_positions)} open positions, market state ${display(centre.market_state)}.`;
}

function renderPrimaryTabs() {
  const container = document.getElementById("primaryTabs");
  const tabs = state.mode === "operator" ? OPERATOR_TABS : ENGINEERING_TABS;
  container.innerHTML = tabs.map(tab => `
    <button type="button" class="nav-button ${state.activeTab === tab.key ? "is-active" : ""}" data-tab="${tab.key}">
      <span class="nav-label">${escapeHtml(tab.label)}</span>
      <span class="nav-copy">${escapeHtml(tab.description)}</span>
    </button>
  `).join("");
  container.querySelectorAll(".nav-button").forEach(button => {
    button.addEventListener("click", () => {
      state.activeTab = button.dataset.tab;
      updateVisibleWorkspace();
      renderPrimaryTabs();
    });
  });
}

function switchMode(mode) {
  state.mode = mode;
  const tabs = mode === "operator" ? OPERATOR_TABS : ENGINEERING_TABS;
  if (!tabs.some(item => item.key === state.activeTab)) {
    state.activeTab = tabs[0].key;
  }
  document.getElementById("modeOperator").classList.toggle("is-active", mode === "operator");
  document.getElementById("modeEngineering").classList.toggle("is-active", mode === "engineering");
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

function renderOverview() {
  const projection = state.projection;
  renderMetricCards("statusGrid", projection.command_centre || {});
  const narrative = document.getElementById("overviewNarrative");
  const selected = getSelectedStrategy();
  const alerts = projection.alerts || [];
  const facts = projection.decision_explanations || [];
  narrative.innerHTML = [
    summaryRow("Enabled strategies", `${display(projection.command_centre?.enabled_strategy_instances)} configured for this snapshot.`),
    summaryRow("Decision facts", `${display(facts.length)} immutable explainability facts are available for operator review.`),
    summaryRow("Selected strategy", selected ? `${selected.identity.strategy} ${selected.identity.instrument} is loaded in the Decision Explorer.` : "Select a strategy to open the Decision Explorer."),
    summaryRow("Alerts", alerts.length ? `${alerts.length} active alert(s) require attention.` : "No active alerts in this snapshot."),
  ].join("");

  const authoritySummary = document.getElementById("authoritySummary");
  authoritySummary.innerHTML = renderKeyValuePairs({
    Session: projection.system?.session,
    "Broker order authority": projection.system?.broker_order_authority,
    "System state": projection.command_centre?.system_state,
    "Market state": projection.command_centre?.market_state,
    "Projection hash": projection.projection_hash,
    "Decision explainability facts": facts.length,
    "Unprotected positions": projection.command_centre?.unprotected_positions,
    "Critical alerts": projection.command_centre?.critical_alerts,
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

  populatePanelList("commandCentreStrategyHealth", projection.command_centre?.strategy_health || [], item => ({
    title: `${item.strategy || "Strategy"} ${item.instrument || ""}`.trim(),
    data: {
      Health: item.health,
      Evidence: item.evidence,
      "Current action": item.current_action,
    },
  }), "No strategy health rows", { Status: "No strategy-health rows available" });

  populatePanelList("commandCentreTimeline", projection.command_centre?.market_session_timeline || [], item => ({
    title: `${item.time || "Time"} / ${item.event || "Event"}`,
    data: {
      Status: item.status,
    },
  }), "No session timeline", { Status: "No session timeline available" });
}

function renderStrategyRail() {
  const strategies = state.projection?.strategies || [];
  document.getElementById("strategyCount").textContent = String(strategies.length);
  const rail = document.getElementById("strategyRail");
  rail.innerHTML = strategies.map(strategy => {
    const strategyId = strategy.identity.instance;
    const completeness = getStrategyCompleteness(strategy);
    const selected = strategyId === state.selectedStrategyId;
    return `
      <button type="button" class="strategy-rail-item ${selected ? "is-selected" : ""}" data-strategy-id="${strategyId}">
        <span class="rail-topline">
          <strong>${escapeHtml(strategy.identity.strategy)} ${escapeHtml(strategy.identity.instrument)}</strong>
          ${badgeMarkup(completeness.badgeTone, completeness.label)}
        </span>
        <span class="rail-meta">${escapeHtml(strategy.state.monthly_status || "Status unavailable")} | ${escapeHtml(strategy.state.branch || "Branch unavailable")}</span>
        <span class="rail-meta">${escapeHtml(strategy.state.runtime_stage || "Runtime stage unavailable")}</span>
      </button>
    `;
  }).join("");
  rail.querySelectorAll(".strategy-rail-item").forEach(item => {
    item.addEventListener("click", () => {
      state.selectedStrategyId = item.dataset.strategyId;
      state.activeTab = "strategies";
      render();
    });
  });
}

function renderWorkbench() {
  const projection = state.projection;
  const strategies = projection?.strategies || [];
  const filter = document.getElementById("strategyFilter").value.trim().toLowerCase();
  const workbench = document.getElementById("strategyWorkbench");
  const filtered = strategies.filter(item => JSON.stringify(item).toLowerCase().includes(filter));
  document.getElementById("strategyWorkbenchSummary").innerHTML = [
    badgeMarkup("neutral", `${strategies.length} configured instance(s)`),
    badgeMarkup("good", `${strategies.filter(item => item.position.health === "OPEN_PROTECTED").length} protected`),
    badgeMarkup("warn", `${strategies.filter(item => getStrategyCompleteness(item).badgeTone === "warn").length} limited explanation`),
    badgeMarkup("bad", `${strategies.filter(item => getStrategyCompleteness(item).badgeTone === "bad").length} missing sections`),
    badgeMarkup("neutral", filter ? `${filtered.length} after filter` : "No filter applied"),
  ].join("");
  workbench.innerHTML = filtered.map(strategy => renderStrategyWorkbenchCard(strategy)).join("");
  workbench.querySelectorAll("[data-strategy-select]").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedStrategyId = button.dataset.strategySelect;
      state.activeTab = "strategies";
      state.explainTab = "overview";
      render();
    });
  });
  renderStrategyFamilies();
}

function renderStrategyWorkbenchCard(strategy) {
  const completeness = getStrategyCompleteness(strategy);
  const strategyId = strategy.identity.instance;
  const alerts = strategy.operations?.alerts || [];
  return `
    <article class="strategy-card ${strategyId === state.selectedStrategyId ? "is-selected" : ""}">
      <div class="card-head">
        <div>
          <p class="section-kicker">${escapeHtml(strategy.identity.strategy)} / ${escapeHtml(strategy.identity.instrument)}</p>
          <h3>${escapeHtml(strategy.identity.account)}</h3>
        </div>
        ${badgeMarkup(completeness.badgeTone, completeness.label)}
      </div>
      <div class="card-chip-row">
        ${badgeMarkup("neutral", strategy.state.monthly_status || "Monthly status unavailable")}
        ${badgeMarkup("neutral", strategy.state.branch || "Branch unavailable")}
        ${badgeMarkup(getHealthTone(strategy.state.health), strategy.state.health || "Health unavailable")}
      </div>
      <div class="card-grid">
        ${infoCell("Runtime stage", strategy.state.runtime_stage)}
        ${infoCell("Selected contract", strategy.plan.selected_contract)}
        ${infoCell("Entry", strategy.plan.base_entry)}
        ${infoCell("Target", strategy.plan.target)}
        ${infoCell("SL", strategy.plan.original_sl)}
        ${infoCell("Evidence", strategy.state.evidence_quality)}
      </div>
      <div class="stage-pill-row">
        ${REQUIRED_STAGE_KEYS.map(key => {
          const stage = getExplainSectionModel(strategy)[key];
          return `<span class="stage-pill tone-${stage.statusTone}">${escapeHtml(stage.shortLabel)}</span>`;
        }).join("")}
      </div>
      <div class="card-footer">
        <div class="card-alert">${alerts.length ? escapeHtml(alerts[0].code) : "No active strategy alert"}</div>
        <button type="button" class="action-button" data-strategy-select="${strategyId}">Explain Decision</button>
      </div>
    </article>
  `;
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

  if (!selected) {
    title.textContent = "Select a strategy";
    healthBadge.className = "badge badge-neutral";
    healthBadge.textContent = "No strategy selected";
    badge.textContent = "";
    summary.innerHTML = `<div class="empty-state">Select one strategy from the left rail or Strategy Workbench.</div>`;
    context.innerHTML = "";
    checklist.innerHTML = "";
    flow.innerHTML = "";
    tabBar.innerHTML = "";
    panel.innerHTML = "";
    return;
  }

  const sectionModel = getExplainSectionModel(selected);
  title.textContent = `${selected.identity.strategy} ${selected.identity.instrument} decision path`;
  healthBadge.className = `badge ${badgeClass(getHealthTone(selected.state.health))}`;
  healthBadge.textContent = selected.state.health || "Health unavailable";
  badge.innerHTML = `${badgeMarkup("neutral", selected.state.runtime_stage || "Runtime stage unavailable")} ${badgeMarkup("neutral", selected.state.evidence_quality || "Evidence unavailable")}`;
  context.innerHTML = renderKeyValuePairs({
    Strategy: selected.identity.strategy,
    Instrument: selected.identity.instrument,
    Account: selected.identity.account,
    Product: selected.identity.product_label,
    Segment: selected.identity.segment_label,
    Broker: selected.identity.broker,
    Session: selected.identity.session,
    "Strategy version": selected.identity.version,
  });
  checklist.innerHTML = buildOperatorChecklist(selected).map(item => checklistItem(item)).join("");

  summary.innerHTML = [
    metricTile("Monthly Status", selected.state.monthly_status),
    metricTile("Branch", selected.state.branch),
    metricTile("Selected Contract", selected.plan.selected_contract),
    metricTile("Entry", selected.plan.base_entry),
    metricTile("Target", selected.plan.target),
    metricTile("Original SL", selected.plan.original_sl),
    metricTile("Order State", selected.execution.order_state),
    metricTile("Position Health", selected.position.health),
  ].join("");

  flow.innerHTML = REQUIRED_STAGE_KEYS.map(key => {
    const item = sectionModel[key];
    return `
      <button type="button" class="flow-step tone-${item.statusTone} ${state.explainTab === key ? "is-active" : ""}" data-explain-tab="${key}">
        <span class="flow-label">${escapeHtml(item.label)}</span>
        <span class="flow-copy">${escapeHtml(item.caption)}</span>
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
    <div class="panel-banner tone-${section.statusTone}">
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
  const timelineFacts = facts.length ? facts : [];
  const rawPrices = planFact?.output_value?.raw_prices || {};
  const normalizedPrices = planFact?.output_value?.normalized_prices || {};
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
      "Independent market-context output used before branch mapping.",
      monthlyFact ? "good" : strategy.state.monthly_status ? "warn" : "bad",
      monthlyFact ? "Explained" : strategy.state.monthly_status ? "Output visible" : "Missing",
      `
        ${renderKeyFactsPanel({
          "Engine monthly status": strategy.state.monthly_status,
          "Plan monthly status": strategy.plan.monthly_status,
          "Instrument": strategy.identity.instrument,
          "Evidence quality": strategy.state.evidence_quality,
          "Rule": monthlyFact?.rule_id || "READ_MODEL_MONTHLY_STATUS",
          "Derivation trace in this snapshot": monthlyFact ? "One immutable backend fact row is available" : "Not emitted as authoritative monthly-candle steps",
        }, "Monthly Status output")}
        ${renderWarningBox("You can verify the final Monthly Status value shown by the backend, but this snapshot does not yet expose the monthly candle chain, transition test, or authoritative derivation steps used by the Monthly Status engine.")}
        ${renderKeyFactsPanel({
          "What is verifiable here": "Returned Monthly Status, strategy branch, evidence quality, source-trace presence",
          "What is not yet verifiable here": "Monthly candle references, continuation test, Bull/Bear transition logic, rule-by-rule derivation",
          "Current operator conclusion": "Treat this tab as final-output evidence only until dedicated Monthly Status engine facts are emitted",
        }, "Verification status")}
        ${renderExplainFactCards([monthlyFact])}
      `
    ),
    branch: buildSection(
      "Branch mapping",
      "How Monthly Status became the selected strategy branch.",
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
      "Historical references and timing windows used by the strategy plan.",
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
      "Expiry, option type, strike, and rejected-candidate evidence.",
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
          "Premium filter result": strategy.plan.premium,
          "OI filter result": strategy.plan.oi,
          "Selection quality": strategy.state.evidence_quality,
          "Operator conclusion": contractFact ? "Contract selection has one immutable fact row" : "Only final contract output is present in this snapshot",
        }, "Operator review")}
        ${renderCandidateTables(evaluatedContracts, rejectedCandidates)}
      `
    ),
    entry: buildSection(
      "Entry Calculation",
      "Raw versus normalized entry values and the rule used to produce them.",
      planFact ? "good" : strategy.plan.base_entry ? "warn" : "bad",
      planFact ? "Explained" : strategy.plan.base_entry ? "Output visible" : "Missing",
      `
        ${renderKeyFactsPanel({
          "Displayed entry": strategy.plan.base_entry,
          "Raw entry": rawPrices.base_entry || "Not emitted in this snapshot",
          "Normalized entry": normalizedPrices.base_entry || strategy.plan.base_entry,
          "Selected contract": strategy.plan.selected_contract,
          "Rule": planFact?.rule_id || "READ_MODEL_PLAN_VALUES",
          "Formula status": "Final output visible; authoritative intermediate formula trace not emitted",
        }, "Entry values")}
        ${renderKeyFactsPanel({
          "Inputs visible here": summarizeObject(strategy.plan.market_references || {}),
          "Target returned by backend": strategy.plan.target,
          "Original SL returned by backend": strategy.plan.original_sl,
          "What this proves": "The backend selected one final entry value for this strategy instance",
          "What it does not prove": "The exact authoritative workbook formula path used to derive Base Entry",
        }, "Explanation quality")}
        ${renderWarningBox("This tab currently explains the final backend output and its surrounding context, but not the full authoritative entry derivation chain. Raw intermediate calculation steps must come from dedicated backend explanation facts, not from frontend inference.")}
        ${renderExplainFactCards([planFact])}
      `
    ),
    "orpt-rc": buildSection(
      "ORPT / RC",
      "Fresh-entry cutoff and recalculation path state.",
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
      "Protection values linked to the effective entry and active position state.",
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
      "Order state, fill state, quantity, and current PositionCycle health.",
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
      "Realized and unrealized P&L from the current read model.",
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
      "Chronological immutable decision events for this strategy instance.",
      timelineFacts.length ? "neutral" : "warn",
      timelineFacts.length ? "Available" : "Limited",
      renderTimeline(timelineFacts, strategy)
    ),
    manual: buildSection(
      "Manual Comparison",
      "Local-only operator comparison. Manual values never mutate runtime truth.",
      "neutral",
      "Validation only",
      renderManualComparison(strategy, manualRows)
    ),
    "source-trace": buildSection(
      "Source Trace",
      "Workbook and rule references attached to immutable backend facts.",
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
      Account: strategy.identity.account,
      "Monthly Status": strategy.state.monthly_status,
      Branch: strategy.state.branch,
      "Runtime stage": strategy.state.runtime_stage,
      "Selected contract": strategy.plan.selected_contract,
      "Explainability completeness": completeness.label,
      "Decision fact count": facts.length,
    }, "Current engine result")}
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
    <div class="fact-card-grid">
      ${list.map(item => `
        <article class="fact-card">
          <div class="fact-head">
            <strong>${escapeHtml(item.stage || "Stage")}</strong>
            ${badgeMarkup(item.rejection_reason ? "warn" : "neutral", item.rule_id || "Rule unavailable")}
          </div>
          <div class="fact-body">
            <p><strong>Formula:</strong> ${escapeHtml(item.formula_text || "Unavailable")}</p>
            <p><strong>Workbook:</strong> ${escapeHtml(item.workbook_source || "Unavailable")}</p>
            <p><strong>Evidence:</strong> ${escapeHtml([item.evidence_source, item.evidence_quality, item.evidence_mode].filter(Boolean).join(" / "))}</p>
            <p><strong>Inputs:</strong> ${escapeHtml(summarizeObject(item.input_values || {}))}</p>
            <p><strong>Outputs:</strong> ${escapeHtml(summarizeObject(item.output_value || {}))}</p>
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
  target.innerHTML = `
    ${renderKeyFactsPanel({
      "Instrument": selected.identity.instrument,
      "Trading date": selected.identity.session,
      "Final Status": selected.state.monthly_status_label || selected.state.monthly_status,
      "Evidence Quality": selected.state.evidence_quality_label || selected.state.evidence_quality,
      "Rule": monthlyFact?.rule_id || "READ_MODEL_MONTHLY_STATUS",
      "Source Completeness": monthlyFact ? "Partial runtime fact" : "Missing",
    }, "Monthly Status review")}
    ${renderWarningBox("Monthly Status is rendered from backend facts only. Candle-by-candle monthly derivation, rule truth table, and transition sequence are not yet emitted in this snapshot and therefore cannot be independently re-verified here.")}
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

function renderOrders() {
  const projection = state.projection;
  const orders = projection.orders || [];
  const summary = document.getElementById("ordersSummary");
  summary.innerHTML = [
    badgeMarkup("neutral", `${orders.length} order row(s)`),
    badgeMarkup("good", `${orders.filter(item => item.state === "FILLED_INTERNAL").length} filled`),
    badgeMarkup("warn", `${orders.filter(item => item.warning_or_error || item.failure).length} with warning`),
    badgeMarkup("neutral", `${orders.filter(item => item.state === "NO_ORDER").length} no-order`),
  ].join("");
  renderTable("ordersTable", orders.map(o => [
    o.account,
    o.strategy,
    o.instance,
    o.position_cycle,
    o.instrument,
    o.contract,
    `${o.side || ""} / ${o.purpose}`,
    o.generation,
    o.requested_quantity,
    o.filled_quantity,
    o.price,
    o.status_label || o.state,
    o.age,
    o.latest_event,
    o.warning_or_error || o.failure || "",
  ]));
}

function renderPositions() {
  const projection = state.projection;
  const positions = projection.positions || [];
  const summary = document.getElementById("positionsSummary");
  summary.innerHTML = [
    badgeMarkup("neutral", `${positions.length} position row(s)`),
    badgeMarkup("good", `${positions.filter(item => item.health === "OPEN_PROTECTED").length} protected`),
    badgeMarkup("warn", `${positions.filter(item => item.protection_status !== "PROTECTED").length} missing protection`),
    badgeMarkup("neutral", `${positions.filter(item => item.fresh_or_carried === "CARRIED").length} carried`),
  ].join("");
  renderTable("positionsTable", positions.map(o => [
    o.account,
    o.strategy,
    o.instrument,
    o.contract,
    o.fresh_or_carried_label || o.fresh_or_carried,
    o.quantity,
    o.average_entry,
    o.mark,
    o.target,
    o.active_sl,
    o.protection_label || o.protection_status,
    o.realized_pnl,
    o.unrealized_pnl,
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
    accountsPanel.appendChild(panel(account.account_reference, {
      Status: projection.state_labels?.[account.status]?.label || account.status,
      "Accepted instances": account.accepted_instances?.length,
      "Rejected instances": account.rejected_instances?.length,
      "Available margin": account.limits?.available_margin,
      "Reserved margin": account.limits?.reserved_margin,
      "Used margin": account.usage?.used_margin,
      "Margin usage %": account.usage?.margin_usage_pct,
    }));
    configPanel.appendChild(panel(account.account_reference, {
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
  const hiddenKeys = new Set([
    "critical_alert_rows",
    "recent_operational_events",
    "strategy_health",
    "pending_actions",
    "active_trades",
    "market_session_timeline",
    "account_summary",
  ]);
  target.innerHTML = Object.entries(payload || {}).filter(([key]) => !hiddenKeys.has(key)).slice(0, 12).map(([key, value]) => `
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
    section.style.display = section.id === `tab-${state.activeTab}` ? "" : "none";
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

function getSelectedStrategy() {
  return (state.projection?.strategies || []).find(item => item.identity.instance === state.selectedStrategyId) || null;
}

function getFactsForStrategy(strategyInstanceId) {
  return (state.projection?.decision_explanations || []).filter(item => item.strategy_instance_id === strategyInstanceId);
}

function summaryRow(labelText, value) {
  return `<div class="summary-row"><span>${escapeHtml(labelText)}</span><strong>${escapeHtml(value)}</strong></div>`;
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

function isTrustedMarkup(value) {
  if (typeof value !== "string") {
    return false;
  }
  return value.includes("<input") || value.includes('class="badge');
}

function formatCell(cell, multiline) {
  if (cell === null || cell === undefined) {
    return "";
  }
  const raw = String(cell);
  if (raw.includes("<input")) {
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
  if (Array.isArray(value)) return value.map(item => display(item)).join(", ");
  if (typeof value === "object") return summarizeObject(value);
  return formatDisplayString(String(value));
}

function formatDisplayString(raw) {
  if (!raw) return "";
  if (/^\d{2}:\d{2}:\d{2}\.\d+$/.test(raw)) {
    return formatClockValue(raw);
  }
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/.test(raw)) {
    return formatIsoDateTime(raw);
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
  const milli = micros ? `.${micros.slice(0, 3).padEnd(3, "0")}` : "";
  return `${String(hour).padStart(2, "0")}:${minutes}:${seconds}${milli} ${suffix}`;
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
  return String(key).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function toggleTheme() {
  document.body.classList.toggle("dark");
}

init();
