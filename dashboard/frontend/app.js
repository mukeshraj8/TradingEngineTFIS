const state = { projection: null, sort: {} };

const columns = {
  strategyTable: ["Strategy", "Instrument", "Account", "Monthly Status", "Branch", "Runtime Stage", "Selected Contract", "Entry", "Target", "SL", "Order", "Position", "P&L", "Health"],
  premarketTable: ["Strategy", "Metadata", "Market Structure", "Candidates", "Selected Contract", "Expiry", "Premium", "OI", "Entry", "Target", "SL", "ORPT", "RC", "Evidence", "Block Reason"],
  ordersTable: ["Account", "Strategy", "Instance", "PositionCycle", "Instrument", "Contract", "Purpose", "Generation", "Requested", "Filled", "Price", "State", "Age", "Latest Event", "Failure"],
  positionsTable: ["Account", "Strategy", "Instrument", "Contract", "Fresh/Carried", "Quantity", "Average Entry", "Mark", "Target", "Active SL", "Protection", "Realized", "Unrealized", "Exit Deadline", "Health"],
  explainabilityTable: ["Strategy", "Instrument", "Stage", "Rule", "Workbook", "Formula", "Inputs", "Output", "Rejections", "Evidence", "Eligibility"],
  auditTable: ["Operator", "Timestamp", "Command", "Scope", "Reason", "Preview", "Result", "Previous", "New", "Evidence Hash"]
};

async function loadProjection() {
  const response = await fetch("api/snapshot.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Snapshot request failed: ${response.status}`);
  }
  state.projection = await response.json();
  render();
}

function render() {
  const p = state.projection;
  document.getElementById("authorityBadge").textContent = `Broker order authority: ${p.system.broker_order_authority}`;
  renderMetrics("statusGrid", p.command_centre);
  renderStrategies(p.strategies);
  renderPremarket(p.strategies);
  renderTable("ordersTable", p.orders.map(o => [o.account, o.strategy, o.instance, o.position_cycle, o.instrument, o.contract, o.purpose, o.generation, o.requested_quantity, o.filled_quantity, o.price, o.state, o.age, o.latest_event, o.failure || ""]));
  renderTable("positionsTable", p.positions.map(o => [o.account, o.strategy, o.instrument, o.contract, o.fresh_or_carried, o.quantity, o.average_entry, o.mark, o.target, o.active_sl, o.protection_status, o.realized_pnl, o.unrealized_pnl, o.exit_deadline, o.health]));
  renderAccounts(p.accounts);
  renderMetrics("analyticsGrid", p.analytics);
  renderExplainability(p.decision_explanations || []);
  renderAlerts(p.alerts);
  renderTable("auditTable", p.audit.map(a => [a.operator, a.timestamp, a.command, a.scope, a.reason, String(a.preview), a.result, a.previous_state, a.new_state, a.evidence_hash]));
  document.getElementById("settingsBlock").textContent = JSON.stringify({ system: p.system, projection_hash: p.projection_hash }, null, 2);
}

function renderMetrics(id, payload) {
  const target = document.getElementById(id);
  target.innerHTML = "";
  Object.entries(payload).slice(0, 24).forEach(([key, value]) => {
    const card = document.createElement("div");
    card.className = "metric";
    card.innerHTML = `<span>${label(key)}</span><strong>${display(value)}</strong>`;
    target.appendChild(card);
  });
}

function renderStrategies(strategies) {
  const term = document.getElementById("strategyFilter").value.toLowerCase();
  const rows = strategies
    .filter(item => JSON.stringify(item.identity).toLowerCase().includes(term) || JSON.stringify(item.state).toLowerCase().includes(term))
    .map(item => [
      item.identity.strategy,
      item.identity.instrument,
      item.identity.account,
      item.state.monthly_status,
      item.state.branch,
      item.state.runtime_stage,
      item.plan.selected_contract,
      item.plan.base_entry,
      item.plan.target,
      item.plan.original_sl,
      item.execution.order_state,
      item.position.health,
      `${item.accounting.realized_pnl} / ${item.accounting.unrealized_pnl}`,
      item.state.health
    ]);
  renderTable("strategyTable", rows);
}

function renderPremarket(strategies) {
  renderTable("premarketTable", strategies.map(item => [
    item.identity.strategy,
    item.state.evidence_quality,
    display(item.plan.market_references),
    item.plan.candidate_contract_count || "source projection",
    item.plan.selected_contract,
    display(item.plan.expiry_candidates),
    item.plan.premium,
    item.plan.oi,
    item.plan.base_entry,
    item.plan.target,
    item.plan.original_sl,
    item.plan.orpt,
    item.plan.rc,
    item.plan.evidence_quality,
    item.plan.block_reason || ""
  ]));
}

function renderAccounts(accounts) {
  const accountsPanel = document.getElementById("accountsPanel");
  const riskPanel = document.getElementById("riskPanel");
  accountsPanel.innerHTML = "";
  riskPanel.innerHTML = "";
  accounts.forEach(account => {
    accountsPanel.appendChild(panel(account.account_reference, {
      Status: account.status,
      Accepted: account.accepted_instances.length,
      Rejected: account.rejected_instances.length,
      "Projection Hash": account.projection_hash
    }));
    riskPanel.appendChild(panel("Limits / Usage", { ...account.limits, ...account.usage }));
  });
}

function renderAlerts(alerts) {
  const target = document.getElementById("alertsPanel");
  target.innerHTML = "";
  if (!alerts.length) {
    target.appendChild(panel("No Active Alerts", { Status: "CLEAR" }));
    return;
  }
  alerts.forEach(alert => target.appendChild(panel(alert.code || "Alert", alert)));
}

function renderExplainability(facts) {
  const term = document.getElementById("explainabilityFilter").value.toLowerCase();
  const rows = facts
    .filter(item => JSON.stringify(item).toLowerCase().includes(term))
    .map(item => [
      item.strategy_instance_id,
      item.instrument,
      item.stage,
      item.rule_id,
      item.workbook_source,
      item.formula_text,
      summarizeObject(item.input_values),
      summarizeObject(item.output_value),
      summarizeObject(item.candidate_evidence?.rejected_candidates || item.candidate_evidence || {}),
      `${item.evidence_source} / ${item.evidence_quality} / ${item.evidence_mode}`,
      item.rejection_reason || item.output_value?.current_entry_state || ""
    ]);
  renderTable("explainabilityTable", rows);
}

function renderTable(id, rows) {
  const table = document.getElementById(id);
  const head = columns[id].map((name, index) => `<th data-index="${index}">${name}</th>`).join("");
  const body = rows.map(row => `<tr>${row.map(cell => `<td>${escapeHtml(display(cell))}</td>`).join("")}</tr>`).join("");
  table.innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
  table.querySelectorAll("th").forEach(th => th.addEventListener("click", () => sortTable(id, Number(th.dataset.index))));
}

function sortTable(id, index) {
  const rows = Array.from(document.querySelectorAll(`#${id} tbody tr`));
  const asc = state.sort[id] !== index;
  state.sort[id] = asc ? index : -index;
  rows.sort((a, b) => a.children[index].textContent.localeCompare(b.children[index].textContent) * (asc ? 1 : -1));
  const body = document.querySelector(`#${id} tbody`);
  rows.forEach(row => body.appendChild(row));
}

function panel(title, data) {
  const item = document.createElement("div");
  item.className = "panel";
  const pairs = Object.entries(data).map(([key, value]) => `<span>${escapeHtml(label(key))}</span><span>${escapeHtml(display(value))}</span>`).join("");
  item.innerHTML = `<h3>${escapeHtml(title)}</h3><div class="kv">${pairs}</div>`;
  return item;
}

function display(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return Array.isArray(value) ? value.join(", ") : JSON.stringify(value);
  return String(value);
}

function summarizeObject(value) {
  if (value === null || value === undefined) return "";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) {
    if (!value.length) return "";
    return value.map(item => typeof item === "object" ? JSON.stringify(item) : String(item)).join(" | ");
  }
  return Object.entries(value).map(([key, item]) => `${key}: ${display(item)}`).join(" | ");
}

function label(key) {
  return String(key).replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.getElementById("themeToggle").addEventListener("click", () => document.body.classList.toggle("dark"));
document.getElementById("strategyFilter").addEventListener("input", () => renderStrategies(state.projection.strategies));
document.getElementById("explainabilityFilter").addEventListener("input", () => renderExplainability(state.projection.decision_explanations || []));
loadProjection().catch(error => {
  document.body.innerHTML = `<main class="section"><h1>Dashboard unavailable</h1><pre>${escapeHtml(error.message)}</pre></main>`;
});
setInterval(() => {
  loadProjection().catch(() => {});
}, 5000);
