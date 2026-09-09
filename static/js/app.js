"use strict";

// HTTP envelopes are documented in docs/API_FRONTEND.md.
const byId = (id) => document.getElementById(id);
const euro = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 });
const money = (cents) => Number.isSafeInteger(cents) ? euro.format(cents / 100) : "Non disponible";
const duration = (ms) => typeof ms === "number" && Number.isFinite(ms) && ms >= 0
  ? `${number.format(ms)} ms` : "Non disponible";
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

const NOT_AVAILABLE = "Non disponible";
const REQUEST_STATES = Object.freeze({
  verified: ["✓ Réponse vérifiée", "verified"],
  unverified: ["! Réponse non validée", "unverified"],
  needs_clarification: ["? Demande de précision", "clarification"],
  security_refusal: ["⛔ Refus de sécurité", "refusal"],
  refused: ["⛔ Refus", "refusal"],
  error: ["× Erreur technique", "technical-error"],
});
const CONFIDENCE_LEVELS = Object.freeze({
  high: ["Confiance élevée", "verified"],
  medium: ["Confiance moyenne", "medium"],
  low: ["Confiance faible", "unverified"],
  uncertain: ["Incertitude / information insuffisante", "clarification"],
  insufficient_information: ["Incertitude / information insuffisante", "clarification"],
  refused: ["Refus", "refusal"],
  error: ["Erreur", "technical-error"],
});
const requestValue = (value) => value === null || value === undefined ? NOT_AVAILABLE : String(value);
const requestCount = (value) => Number.isSafeInteger(value) && value >= 0 ? value : null;
const knownValue = (table, value) => typeof value === "string" && Object.hasOwn(table, value) ? value : null;

// Optional, allowlisted presentation contract; an invalid field never hides its valid siblings.
function validateRequestInfo(data) {
  const payload = isObject(data) ? data : {};
  const info = isObject(payload.request_info) ? payload.request_info : {};
  const metrics = isObject(info.metrics) ? info.metrics : {};
  const state = Object.hasOwn(info, "status") ? knownValue(REQUEST_STATES, info.status)
    : Object.hasOwn(payload, "status") ? knownValue(REQUEST_STATES, payload.status)
    : payload.verdict === "concordance" ? "verified" : payload.verdict === "divergence" ? "unverified" : null;
  const ms = Object.hasOwn(metrics, "total_duration_ms") ? metrics.total_duration_ms : payload.total_duration_ms;
  const cost = info.cost;
  return {
    state,
    confidence: knownValue(CONFIDENCE_LEVELS, info.confidence),
    metrics: {
      total_duration_ms: typeof ms === "number" && Number.isFinite(ms) && ms >= 0 ? ms : null,
      calls: requestCount(metrics.calls), tool_calls: requestCount(metrics.tool_calls),
      model_calls: requestCount(metrics.model_calls), input_tokens: requestCount(metrics.input_tokens),
      output_tokens: requestCount(metrics.output_tokens), total_tokens: requestCount(metrics.total_tokens),
    },
    // Decimal text preserves backend precision, including trailing zeros. Never round or price tokens here.
    cost: isObject(cost) && typeof cost.amount === "string" && /^\d+(?:\.\d+)?$/.test(cost.amount)
      && typeof cost.currency === "string" && /^[A-Z]{3}$/.test(cost.currency)
      ? { amount: cost.amount, currency: cost.currency } : null,
  };
}

function renderRequestLabel(id, value) {
  status(id, value ? value[0] : NOT_AVAILABLE, `request-label ${value ? value[1] : "unavailable"}`);
}

function renderConfidence(info) {
  // Refusals/errors are explicit server states, never inferred from answer text or HTTP codes.
  const level = info.state === "security_refusal" || info.state === "refused" ? "refused"
    : info.state === "error" ? "error" : info.confidence;
  renderRequestLabel("request-confidence", level ? CONFIDENCE_LEVELS[level] : null);
}

function renderMetrics(metrics) {
  byId("request-duration").textContent = metrics.total_duration_ms === null ? NOT_AVAILABLE : `${metrics.total_duration_ms} ms`;
  for (const [id, field] of Object.entries({
    "request-calls": "calls", "request-tool-calls": "tool_calls", "request-model-calls": "model_calls",
    "request-input-tokens": "input_tokens", "request-output-tokens": "output_tokens", "request-total-tokens": "total_tokens",
  })) byId(id).textContent = requestValue(metrics[field]);
}

function renderCost(cost) {
  byId("request-cost").textContent = cost ? `${cost.amount} ${cost.currency}` : NOT_AVAILABLE;
}

function renderRequestInfo(data, { technicalError = false } = {}) {
  const info = validateRequestInfo(data);
  renderRequestLabel("request-outcome", technicalError && !["refused", "security_refusal", "needs_clarification"].includes(info.state)
    ? REQUEST_STATES.error : info.state ? REQUEST_STATES[info.state] : null);
  renderConfidence(info);
  renderMetrics(info.metrics);
  renderCost(info.cost);
  status("request-info-context", technicalError ? "La requête n’a pas abouti. Informations reçues du serveur ci-dessous."
    : "Dernière requête · informations fournies par le serveur.", "muted");
}

function resetRequestInfo(message = "Aucune information pour cette requête.") {
  renderRequestInfo();
  status("request-info-context", message, "muted");
}

function setRequestInfoOpen(open) {
  byId("request-info").hidden = !open;
  byId("request-info-toggle").setAttribute("aria-expanded", String(open));
}

function isRequestBlocked(data) {
  return ["needs_clarification", "refused", "security_refusal", "error"].includes(validateRequestInfo(data).state);
}

function requestMessageKind(data, fallback = "") {
  const state = validateRequestInfo(data).state;
  return isRequestBlocked(data) ? `request-label ${REQUEST_STATES[state][1]}` : fallback;
}

// Defence in depth for existing traces too. The server must only send public, redacted text.
function publicBackendData(value) {
  if (typeof value === "string") return value
    .replace(/\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._~+\/-]+=*)/gi, "[secret masqué]");
  if (Array.isArray(value)) return value.map(publicBackendData);
  if (!isObject(value)) return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) => !/^(?:.*api_?key|authorization|.*secret.*|access_?token|refresh_?token|token|system_?prompts?|system|password|credentials)$/i.test(key))
    .map(([key, item]) => [key, publicBackendData(item)]));
}

function status(id, message, kind = "") {
  byId(id).textContent = message;
  byId(id).className = kind;
}

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    // HTTP status takes precedence, including HTML error pages from Flask.
    if (!response.ok) {
      let failure;
      try { failure = publicBackendData(await response.json()); } catch { /* Keep the HTTP fallback. */ }
      let message;
      if (typeof failure?.error?.message === "string") message = failure.error.message;
      else if (path === "/imports" && [400, 413, 415, 422].includes(response.status)) {
        message = "Fichier invalide, trop volumineux ou format non pris en charge.";
      } else if (response.status === 404) message = "Ressource introuvable (HTTP 404).";
      else if (response.status >= 500) message = `Erreur serveur (${response.status}). Réessayez plus tard.`;
      else message = `La demande a été refusée (HTTP ${response.status}).`;
      const error = new Error(message);
      error.httpStatus = response.status;
      error.backendData = failure;
      throw error;
    }
    let data;
    try { data = publicBackendData(await response.json()); }
    catch { throw new Error("Le serveur a renvoyé une réponse JSON invalide."); }
    if (!isObject(data) && !Array.isArray(data)) throw new Error("Format de réponse inattendu.");
    if (data.ok === false) {
      const error = new Error(typeof data.error?.message === "string" ? data.error.message : "Le backend a signalé une erreur.");
      error.backendData = data;
      throw error;
    }
    if (data.ok === true && isObject(data.value)) {
      const value = { ...data.value };
      for (const key of ["request_info", "total_duration_ms"]) {
        if (!Object.hasOwn(value, key) && Object.hasOwn(data, key)) value[key] = data[key];
      }
      return value;
    }
    return data.ok === true ? data.value : data;
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("Délai de réponse dépassé. Vérifiez l'état du serveur avant de renouveler l'envoi.");
    }
    if (error instanceof TypeError) throw new Error("Backend injoignable. Vérifiez votre connexion et le lancement du serveur.");
    throw error;
  } finally { clearTimeout(timeout); }
}

function paragraph(parent, text) {
  const element = document.createElement("p");
  element.textContent = text;
  parent.append(element);
}

function expenseTable(parent, expenses, caption) {
  if (!Array.isArray(expenses)) throw new Error("Liste des dépenses invalide dans la réponse du serveur.");
  if (!expenses.every((item) => isObject(item) && Number.isSafeInteger(item.id) && item.id > 0
      && typeof item.date === "string" && typeof item.description === "string"
      && typeof item.category === "string" && Number.isSafeInteger(item.amount_cents))) {
    throw new Error("Une dépense reçue possède un format invalide.");
  }
  if (!expenses.length) { paragraph(parent, "Aucune dépense."); return; }
  const table = document.createElement("table");
  const title = document.createElement("caption");
  title.textContent = caption;
  table.append(title);
  const head = document.createElement("thead");
  const headings = document.createElement("tr");
  for (const label of ["Identifiant", "Date", "Description", "Catégorie", "Montant"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    headings.append(cell);
  }
  head.append(headings);
  table.append(head);
  const body = document.createElement("tbody");
  for (const expense of expenses) {
    const row = document.createElement("tr");
    for (const value of [expense.id, expense.date, expense.description, expense.category, money(expense.amount_cents)]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    }
    body.append(row);
  }
  table.append(body);
  parent.append(table);
}

async function busy(button, statusId, message, action) {
  const buttons = [button];
  if (["import-status", "chat-status"].includes(statusId)) {
    buttons.push(byId("import-form").querySelector("button"), byId("chat-form").querySelector("button"));
  }
  buttons.forEach((item) => { item.disabled = true; });
  button.setAttribute("aria-busy", "true");
  status(statusId, message);
  try { await action(); }
  catch (error) {
    if (statusId === "chat-status") renderRequestInfo(error.backendData, { technicalError: true });
    status(statusId, error.message, statusId === "chat-status" ? requestMessageKind(error.backendData, "error") : "error");
  }
  finally {
    buttons.forEach((item) => { item.disabled = false; });
    button.removeAttribute("aria-busy");
  }
}

let expenseLoad = Promise.resolve();
let currentExpenses = [];
function renderExpenseList() {
  const query = (byId("expense-search").value || "").trim().toLocaleLowerCase("fr");
  const category = byId("category-filter").value || "";
  const visible = currentExpenses.filter((expense) => (!category || expense.category === category)
    && [expense.description, expense.category, expense.date, String(expense.id)]
      .some((value) => value.toLocaleLowerCase("fr").includes(query)));
  byId("expenses-list").replaceChildren();
  expenseTable(byId("expenses-list"), visible, "Dépenses du jeu de données courant");
  byId("expenses-count").textContent = `(${visible.length} / ${currentExpenses.length})`;
}
function updateCategoryFilter() {
  const filter = byId("category-filter");
  const selected = filter.value;
  filter.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "Toutes les catégories";
  filter.append(all);
  const categories = [...new Set(currentExpenses.map((expense) => expense.category))].sort((a, b) => a.localeCompare(b, "fr"));
  for (const category of categories) {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    filter.append(option);
  }
  filter.value = categories.includes(selected) ? selected : "";
}
function refreshExpenses() {
  byId("expenses-list").replaceChildren();
  currentExpenses = [];
  byId("expenses-count").textContent = "";
  expenseLoad = busy(byId("expenses-refresh"), "expenses-status", "Chargement des dépenses…", async () => {
    const data = await api("/expenses");
    const expenses = Array.isArray(data) ? data : data?.expenses;
    // Validate the server data before keeping it for presentation-only filters.
    expenseTable(document.createElement("div"), expenses, "Dépenses");
    currentExpenses = expenses;
    updateCategoryFilter();
    renderExpenseList();
    status("expenses-status", "Dépenses actualisées.", "success");
  });
  return expenseLoad;
}

function renderTool(id, tool, expenses) {
  const container = byId(id);
  container.replaceChildren();
  if (!isObject(tool)) { paragraph(container, "Résultat non disponible."); return; }
  if (tool.ok === false) {
    paragraph(container, typeof tool.error?.message === "string" ? tool.error.message : "Échec du calcul.");
    return;
  }
  const result = tool.ok === true ? tool.value : tool;
  if (!isObject(result)) { paragraph(container, "Résultat non disponible."); return; }
  paragraph(container, `Résultat : ${money(result.result_cents)}`);
  paragraph(container, `Durée : ${duration(result.duration_ms)}`);
  const ids = result.expense_ids;
  if (!Array.isArray(ids) || !ids.every((id) => Number.isSafeInteger(id) && id > 0)) {
    paragraph(container, "Identifiants des dépenses non disponibles.");
    return;
  }
  paragraph(container, `Dépenses utilisées (identifiants) : ${ids.length ? ids.join(", ") : "aucune"}`);
  if (Array.isArray(expenses)) {
    // Display server-selected evidence; no filtering for financial operations here.
    expenseTable(container, expenses.filter((expense) => ids.includes(expense?.id)), "Détail des dépenses utilisées");
    if (ids.some((id) => !expenses.some((expense) => expense?.id === id))) {
      paragraph(container, "Le serveur n'a pas fourni le détail de toutes les dépenses utilisées.");
    }
  }
}

// Only render the trace supplied by the server, never infer tool calls.
function renderToolTrace(trace) {
  const section = byId("tool-trace");
  const list = byId("tool-trace-list");
  list.replaceChildren();
  section.hidden = true;
  syncTraceEmpty();
  if (!Array.isArray(trace) || !trace.length) return;
  const display = (value) => typeof value === "string" ? value : JSON.stringify(value);
  trace.forEach((call, index) => {
    const block = document.createElement("article");
    block.className = "tool-trace-call";
    const title = document.createElement("h3");
    title.textContent = `Appel ${index + 1}`;
    block.append(title);
    list.append(block);
    if (!isObject(call)) {
      paragraph(block, "Trace invalide reçue du backend.");
      return;
    }
    paragraph(block, `Outil : ${typeof call.tool === "string" ? call.tool : "Non disponible"}`);
    paragraph(block, "Arguments :");
    if (isObject(call.arguments)) {
      for (const [key, value] of Object.entries(call.arguments)) {
        paragraph(block, `${key} : ${display(value)}`);
      }
    } else {
      paragraph(block, "Arguments non disponibles.");
    }
    const state = document.createElement("p");
    state.textContent = call.status === "success" ? "Statut : succès"
      : call.status === "error" ? "Statut : erreur" : "Statut : non disponible";
    state.className = call.status === "error" ? "error" : call.status === "success" ? "success" : "";
    block.append(state);
    if (call.status === "error") {
      const failure = document.createElement("div");
      failure.className = "error";
      if (typeof call.error?.code === "string") paragraph(failure, `Code : ${call.error.code}`);
      paragraph(failure, `Message : ${typeof call.error?.message === "string" ? call.error.message : "Échec de l’outil."}`);
      block.append(failure);
      return;
    }
    if (call.status !== "success") return;
    paragraph(block, "Résultat :");
    if (isObject(call.result)) {
      for (const [key, value] of Object.entries(call.result)) {
        const label = key === "verdict" ? "Verdict" : key === "result_cents" ? "Montant" : key;
        paragraph(block, `${label} : ${key === "result_cents" ? money(value) : display(value)}`);
      }
    } else {
      paragraph(block, Object.hasOwn(call, "result") ? display(call.result) : "Résultat non disponible.");
    }
  });
  section.hidden = false;
  syncTraceEmpty();
}

function syncTraceEmpty() {
  byId("trace-empty").hidden = !byId("tool-trace").hidden || !byId("live-execution").hidden;
}

function resetAnalysis() {
  resetRequestInfo();
  byId("results").hidden = true;
  byId("answer-card").hidden = true;
  byId("comparison-empty").hidden = false;
  status("comparison-badge", "En attente", "badge");
}

function renderAnswer(data) {
  renderRequestInfo(data);
  byId("answer-card").hidden = false;
  byId("answer").textContent = typeof data.answer === "string" ? data.answer
    : typeof data.message === "string" ? data.message : "Réponse finale non disponible.";
  byId("answer-summary").hidden = true;
  byId("answer-details").hidden = byId("results").hidden;
  const unvalidated = validateRequestInfo(data).state === "unverified";
  const concordant = data.verdict === "concordance" && !unvalidated && !isRequestBlocked(data);
  byId("answer-context").textContent = concordant ? "Vérification confirmée par les deux méthodes de calcul."
    : "Consultez les informations renvoyées par le serveur.";
  status("answer-verdict", concordant ? "Python + SQL : concordance"
    : data.verdict === "divergence" ? "Python + SQL : divergence — résultat non validé"
      : unvalidated ? "Réponse non validée par le backend." : "Verdict non disponible.",
    concordant ? "success" : data.verdict === "divergence" ? "error" : "muted");
  // Read only the server-validated result, never sum expenses or compare methods.
  const value = data.python?.ok === true ? data.python.value : data.python;
  const sql = data.sql?.ok === true ? data.sql.value : data.sql;
  if (!concordant || data.python?.ok === false || data.sql?.ok === false
      || !isObject(value) || !isObject(sql) || !Number.isSafeInteger(value.result_cents)
      || !Number.isSafeInteger(sql.result_cents)) return;
  byId("answer-summary").hidden = false;
  byId("summary-category").textContent = typeof data.request?.category === "string" ? data.request.category
    : data.request?.category === null ? "Toutes catégories" : "Non disponible";
  byId("summary-count").textContent = Array.isArray(value.expense_ids)
    && value.expense_ids.every((id) => Number.isSafeInteger(id) && id > 0) ? String(value.expense_ids.length) : "Non disponible";
  byId("summary-amount").textContent = money(value.result_cents);
}

function renderMethodSummary(name, tool) {
  const value = tool?.ok === true ? tool.value : tool;
  const failed = tool?.ok === false;
  byId(`${name}-amount`).textContent = failed ? "Échec" : money(value?.result_cents);
  byId(`${name}-duration`).textContent = `Durée : ${duration(failed ? null : value?.duration_ms)}`;
}

function renderCalculation(data, { preserveLiveTrace = false } = {}) {
  if (!isObject(data)) throw new Error("Format de résultat inattendu.");
  if (isRequestBlocked(data)) {
    resetAnalysis();
    if (!preserveLiveTrace) renderToolTrace(data.tool_trace);
    renderAnswer(data);
    return;
  }
  byId("answer").textContent = typeof data.answer === "string" ? data.answer : "Réponse finale non disponible.";
  const verdict = validateRequestInfo(data).state === "unverified" && data.verdict === "concordance" ? "unverified" : data.verdict;
  const verdicts = { concordance: "Concordance confirmée par le backend.", divergence: "Divergence signalée par le backend : résultat non validé.",
    unverified: "Réponse non validée par le backend." };
  status("verdict", Object.hasOwn(verdicts, verdict) ? verdicts[verdict] : "Verdict non disponible : résultat non validé.",
    verdict === "divergence" ? "error" : verdict === "concordance" ? "success" : "");
  byId("total-duration").textContent = `Durée totale : ${duration(data.total_duration_ms)}`;
  renderTool("python-result", data.python, data.expenses);
  renderTool("sql-result", data.sql, data.expenses);
  if (!preserveLiveTrace) renderToolTrace(data.tool_trace);
  byId("results").hidden = false;
  byId("comparison-empty").hidden = true;
  status("comparison-badge", verdict === "concordance" ? "✓ Concordance" : verdict === "divergence" ? "Divergence" : "Non validé",
    `badge ${verdict === "concordance" ? "success" : verdict === "divergence" ? "error" : ""}`);
  renderMethodSummary("python", data.python);
  renderMethodSummary("sql", data.sql);
  renderAnswer(data);
}

const OPERATION_LABELS = {
  total: "Total", total_by_category: "Total par catégorie", total_by_period: "Total par période",
};

// Hidden entirely unless the backend confirms test mode is on (ENABLE_TEST_CONTROLS=1).
async function loadTestOperations() {
  const section = byId("test-operations");
  let states;
  try { states = await api("/test/operations"); }
  catch { section.hidden = true; return; }
  if (!isObject(states) || !Object.keys(states).length) { section.hidden = true; return; }

  const list = byId("test-operations-list");
  list.replaceChildren();
  for (const [operation, enabled] of Object.entries(states)) {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = enabled === true;
    checkbox.dataset.operation = operation;
    label.append(checkbox, ` ${OPERATION_LABELS[operation] ?? operation}`);
    list.append(label);
    checkbox.addEventListener("change", async () => {
      checkbox.disabled = true;
      status("test-operations-status", "Mise à jour…");
      try {
        await api("/test/operations", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ operation, enabled: checkbox.checked }),
        });
        status(
          "test-operations-status",
          `${OPERATION_LABELS[operation] ?? operation} ${checkbox.checked ? "activée" : "désactivée"}.`,
          "success",
        );
      } catch (error) {
        checkbox.checked = !checkbox.checked;
        status("test-operations-status", error.message, "error");
      } finally {
        checkbox.disabled = false;
      }
    });
  }
  section.hidden = false;
}

async function checkHealth() {
  await busy(byId("health-refresh"), "health-status", "Vérification du backend…", async () => {
    const data = await api("/health");
    if (data?.status !== "ok") throw new Error("Le backend ne confirme pas son bon fonctionnement.");
    status("health-status", "Backend disponible.", "success");
  });
}

const AGENT_API = Object.freeze({
  state: "/agent/state",
  log: "/agent/logs?limit=50",
});
const AGENT_STATES = new Set(["running", "stopped"]);
let currentAgentState = null;

async function getAgentStatus() {
  const data = await api(AGENT_API.state);
  if (!isObject(data) || !AGENT_STATES.has(data.status)) {
    throw new Error("État de l’agent invalide dans la réponse du serveur.");
  }
  return data.status;
}

async function stopAgent() {
  return api(AGENT_API.state, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "stopped" }),
  });
}

async function restartAgent() {
  return api(AGENT_API.state, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: "running" }),
  });
}

function parseAgentLog(data) {
  const entries = Array.isArray(data) ? data : data?.logs;
  if (!Array.isArray(entries) || !entries.every((entry) => isObject(entry)
      && typeof entry.timestamp === "string" && Number.isFinite(Date.parse(entry.timestamp))
      && typeof entry.message === "string")) {
    throw new Error("Journal de l’agent invalide dans la réponse du serveur.");
  }
  return [...entries].sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp));
}

async function getAgentLog() {
  return parseAgentLog(await api(AGENT_API.log));
}

function updateAgentButtons() {
  byId("agent-stop").disabled = currentAgentState !== "running";
  byId("agent-restart").disabled = currentAgentState !== "stopped";
}

function renderAgentState(state) {
  currentAgentState = state;
  const active = state === "running";
  byId("agent-state").textContent = active ? "Agent actif" : "Agent arrêté";
  status("agent-status-badge", active ? "Actif" : "Arrêté", `badge ${active ? "success" : ""}`);
  updateAgentButtons();
}

function renderAgentUnavailable() {
  currentAgentState = null;
  byId("agent-state").textContent = "Contrôle indisponible";
  status("agent-status-badge", "Indisponible", "badge error");
  updateAgentButtons();
}

function renderAgentLog(entries) {
  const container = byId("agent-log");
  container.replaceChildren();
  if (!entries.length) {
    paragraph(container, "Aucune entrée de journal fournie par le backend.");
    return;
  }
  for (const entry of entries) {
    const block = document.createElement("article");
    block.className = "agent-log-entry";
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.timestamp;
    timestamp.textContent = new Date(entry.timestamp).toLocaleString("fr-FR");
    const message = document.createElement("p");
    message.textContent = entry.message;
    block.append(timestamp, message);
    container.append(block);
  }
}

function agentErrorMessage(error, fallback) {
  return [404, 503].includes(error?.httpStatus) ? "Contrôle indisponible." : error?.message || fallback;
}

async function refreshAgentControl(successMessage = "") {
  const [stateResult, logResult] = await Promise.allSettled([getAgentStatus(), getAgentLog()]);
  if (stateResult.status === "fulfilled") renderAgentState(stateResult.value);
  else renderAgentUnavailable();

  if (logResult.status === "fulfilled") renderAgentLog(logResult.value);
  else {
    byId("agent-log").replaceChildren();
    paragraph(byId("agent-log"), agentErrorMessage(logResult.reason, "Journal de l’agent indisponible."));
  }

  if (stateResult.status === "rejected") {
    status("agent-control-message", agentErrorMessage(stateResult.reason, "Contrôle de l’agent indisponible."), "error");
  } else {
    status("agent-control-message", successMessage, successMessage ? "success" : "");
  }
}

async function runAgentAction(button, request, pendingMessage, successMessage) {
  if (button.disabled) return;
  byId("agent-stop").disabled = true;
  byId("agent-restart").disabled = true;
  button.setAttribute("aria-busy", "true");
  status("agent-control-message", pendingMessage);
  try {
    await request();
    await refreshAgentControl(successMessage);
  } catch (error) {
    if ([404, 503].includes(error?.httpStatus)) renderAgentUnavailable();
    else updateAgentButtons();
    status("agent-control-message", agentErrorMessage(error, "Action impossible."), "error");
  } finally {
    button.removeAttribute("aria-busy");
  }
}

byId("import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (event.currentTarget.querySelector("button").disabled) return;
  const file = byId("csv-file").files[0];
  if (!file || !/\.csv$/i.test(file.name) || file.size === 0) {
    status("import-status", "Sélectionnez un fichier CSV non vide. La validation finale est réalisée par le serveur.", "error");
    return;
  }
  await busy(event.currentTarget.querySelector("button"), "import-status", "Import en cours…", async () => {
    const form = new FormData();
    form.append("file", file);
    await api("/imports", { method: "POST", body: form });
    status("import-status", "Import réussi.", "success");
    resetAnalysis();
    renderToolTrace();
    resetStream();
    byId("import-form").reset();
    byId("file-name").textContent = "";
    await expenseLoad;
    await refreshExpenses();
  });
});

byId("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (event.currentTarget.querySelector("button").disabled) return;
  const question = byId("question").value.trim();
  if (!question) { status("chat-status", "Écrivez une question avant de l'envoyer.", "error"); return; }
  resetAnalysis();
  renderToolTrace();
  resetStream();
  resetRequestInfo("Requête en cours · en attente des informations du serveur.");
  byId("request-info-toggle").disabled = false;
  const streaming = byId("stream-mode").checked;
  await busy(event.currentTarget.querySelector("button"), "chat-status", "Analyse en cours…", async () => {
    if (streaming) { await streamQuestion(question); return; }
    let data = await api("/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
    });
    if (isRequestBlocked(data)) {
      renderCalculation(data);
      const state = validateRequestInfo(data).state;
      status("chat-status", typeof data.message === "string" ? data.message : REQUEST_STATES[state][0],
        `request-label ${REQUEST_STATES[state][1]}`);
      if (state === "needs_clarification") byId("question").focus();
      return;
    }
    if (data?.calculation_id !== undefined) {
      const id = data.calculation_id;
      if (!(typeof id === "string" && /^[a-zA-Z0-9_-]+$/.test(id)) && !(Number.isSafeInteger(id) && id > 0)) {
        throw new Error("Identifiant de calcul invalide dans la réponse du serveur.");
      }
      // The detail is authoritative; an omitted optional field keeps the /chat value.
      try {
        const detail = await api(`/calculations/${encodeURIComponent(id)}`);
        if (!isObject(detail)) throw new Error("Format de résultat inattendu.");
        data = { ...data, ...detail };
      }
      catch (error) {
        error.backendData = { ...data, ...error.backendData };
        throw error;
      }
    }
    renderCalculation(data);
    status("chat-status", "Réponse reçue.");
  });
});

byId("stream-cancel").addEventListener("click", () => streamController?.abort());

byId("expenses-refresh").addEventListener("click", refreshExpenses);
byId("health-refresh").addEventListener("click", checkHealth);
byId("agent-stop").addEventListener("click", () => runAgentAction(
  byId("agent-stop"), stopAgent, "Demande d’arrêt en cours…", "Agent arrêté. État actualisé.",
));
byId("agent-restart").addEventListener("click", () => runAgentAction(
  byId("agent-restart"), restartAgent, "Demande de redémarrage en cours…", "Agent redémarré. État actualisé.",
));
checkHealth();
refreshExpenses();
loadTestOperations();
refreshAgentControl();

byId("expense-search").addEventListener("input", renderExpenseList);
byId("request-info-toggle").addEventListener("click", () => {
  if (!byId("request-info-toggle").disabled) setRequestInfoOpen(byId("request-info").hidden);
});
byId("category-filter").addEventListener("change", renderExpenseList);
for (const [id, question] of [["suggest-category", "Combien ai-je dépensé en alimentation ?"], ["suggest-total", "Combien ai-je dépensé au total ?"]]) {
  byId(id).addEventListener("click", () => { byId("question").value = question; byId("question").focus(); });
}
byId("answer-details").addEventListener("click", () => { byId("calculation-details").open = true; });
byId("csv-file").addEventListener("change", () => { byId("file-name").textContent = byId("csv-file").files[0]?.name || ""; });
for (const name of ["dragenter", "dragover"]) {
  byId("drop-zone").addEventListener(name, (event) => { event.preventDefault(); byId("drop-zone").className = "drop-zone dragover"; });
}
byId("drop-zone").addEventListener("dragleave", () => { byId("drop-zone").className = "drop-zone"; });
byId("drop-zone").addEventListener("drop", (event) => {
  event.preventDefault();
  byId("drop-zone").className = "drop-zone";
  if (byId("import-form").querySelector("button").disabled) return;
  const files = event.dataTransfer.files;
  if (files.length !== 1 || !/\.csv$/i.test(files[0].name)) {
    status("import-status", "Déposez un seul fichier CSV.", "error");
    return;
  }
  byId("csv-file").files = files;
  byId("file-name").textContent = files[0].name;
});
window.addEventListener("hashchange", () => {
  const id = window.location.hash.slice(1);
  if (["about", "docs"].includes(id)) byId(id).open = true;
});
