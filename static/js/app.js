"use strict";

// HTTP envelopes are documented in docs/API_FRONTEND.md.
const byId = (id) => document.getElementById(id);
const euro = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const number = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 });
const money = (cents) => Number.isSafeInteger(cents) ? euro.format(cents / 100) : "Non disponible";
const duration = (ms) => typeof ms === "number" && Number.isFinite(ms) && ms >= 0
  ? `${number.format(ms)} ms` : "Non disponible";
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

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
      try { failure = await response.json(); } catch { /* Keep the HTTP fallback. */ }
      if (typeof failure?.error?.message === "string") throw new Error(failure.error.message);
      if (path === "/imports" && [400, 413, 415, 422].includes(response.status)) {
        throw new Error("Fichier invalide, trop volumineux ou format non pris en charge.");
      }
      if (response.status === 404) throw new Error("Ressource introuvable (HTTP 404).");
      if (response.status >= 500) throw new Error(`Erreur serveur (${response.status}). Réessayez plus tard.`);
      throw new Error(`La demande a été refusée (HTTP ${response.status}).`);
    }
    let data;
    try { data = await response.json(); }
    catch { throw new Error("Le serveur a renvoyé une réponse JSON invalide."); }
    if (!isObject(data) && !Array.isArray(data)) throw new Error("Format de réponse inattendu.");
    if (data.ok === false) {
      throw new Error(typeof data.error?.message === "string" ? data.error.message : "Le backend a signalé une erreur.");
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
  catch (error) { status(statusId, error.message, "error"); }
  finally {
    buttons.forEach((item) => { item.disabled = false; });
    button.removeAttribute("aria-busy");
  }
}

let expenseLoad = Promise.resolve();
function refreshExpenses() {
  byId("expenses-list").replaceChildren();
  expenseLoad = busy(byId("expenses-refresh"), "expenses-status", "Chargement des dépenses…", async () => {
    const data = await api("/expenses");
    expenseTable(byId("expenses-list"), Array.isArray(data) ? data : data?.expenses, "Dépenses du jeu de données courant");
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

function renderCalculation(data) {
  if (!isObject(data)) throw new Error("Format de résultat inattendu.");
  byId("answer").textContent = typeof data.answer === "string" ? data.answer : "Réponse finale non disponible.";
  const verdicts = { concordance: "Concordance confirmée par le backend.", divergence: "Divergence signalée par le backend : résultat non validé." };
  status("verdict", Object.hasOwn(verdicts, data.verdict) ? verdicts[data.verdict] : "Verdict non disponible : résultat non validé.",
    data.verdict === "divergence" ? "error" : "");
  byId("total-duration").textContent = `Durée totale : ${duration(data.total_duration_ms)}`;
  renderTool("python-result", data.python, data.expenses);
  renderTool("sql-result", data.sql, data.expenses);
  byId("results").hidden = false;
}

async function checkHealth() {
  await busy(byId("health-refresh"), "health-status", "Vérification du backend…", async () => {
    const data = await api("/health");
    if (data?.status !== "ok") throw new Error("Le backend ne confirme pas son bon fonctionnement.");
    status("health-status", "Backend disponible.", "success");
  });
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
    byId("results").hidden = true;
    byId("import-form").reset();
    await expenseLoad;
    await refreshExpenses();
  });
});

byId("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (event.currentTarget.querySelector("button").disabled) return;
  const question = byId("question").value.trim();
  if (!question) { status("chat-status", "Écrivez une question avant de l'envoyer.", "error"); return; }
  byId("results").hidden = true;
  await busy(event.currentTarget.querySelector("button"), "chat-status", "Analyse en cours…", async () => {
    let data = await api("/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }),
    });
    if (data?.status === "needs_clarification") {
      status("chat-status", typeof data.message === "string" ? data.message : "Veuillez préciser votre question.");
      byId("question").focus();
      return;
    }
    if (data?.calculation_id !== undefined) {
      const id = data.calculation_id;
      if (!(typeof id === "string" && /^[a-zA-Z0-9_-]+$/.test(id)) && !(Number.isSafeInteger(id) && id > 0)) {
        throw new Error("Identifiant de calcul invalide dans la réponse du serveur.");
      }
      data = await api(`/calculations/${encodeURIComponent(id)}`);
    }
    renderCalculation(data);
    status("chat-status", "Réponse reçue.");
  });
});

byId("expenses-refresh").addEventListener("click", refreshExpenses);
byId("health-refresh").addEventListener("click", checkHealth);
checkHealth();
refreshExpenses();
