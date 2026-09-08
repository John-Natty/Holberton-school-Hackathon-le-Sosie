const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.children = []; this.textContent = ''; this.listeners = {}; this.disabled = false; }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
  removeAttribute() {}
  addEventListener(event, callback) { this.listeners[event] = callback; }
  querySelector() { return this.button ??= new Element(); }
  focus() {}
  reset() {}
  get text() { return this.textContent + this.children.map((child) => child.text).join(' '); }
}
function setup() {
  const elements = new Map();
  const get = (id) => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const calls = [];
  const routes = new Map([
    ['/health', { status: 'ok' }], ['/expenses', { expenses: [] }],
  ]);
  const context = vm.createContext({
    document: { getElementById: get, createElement: () => new Element() },
    Intl, AbortController, setTimeout, clearTimeout, FormData, TypeError,
    fetch: async (path, options) => {
      calls.push({ path, options });
      const data = routes.get(path);
      if (data instanceof Error) throw data;
      return { ok: !data?.http, status: data?.http ?? 200,
        json: async () => { if (data?.invalidJson) throw new Error(); return data; } };
    },
  });
  vm.runInContext(fs.readFileSync('static/js/app.js', 'utf8'), context);
  return { context, get, calls, routes, run: (code) => vm.runInContext(code, context) };
}
const expense = { id: 1, date: '2026-09-01', description: '<img src=x onerror=alert(1)>', category: 'Alimentation', amount_cents: 4250 };
const result = { result_cents: 4250, expense_ids: [1], duration_ms: 3.4 };

test('affiche les centimes et les contenus CSV comme texte', () => {
  const env = setup();
  env.context.payload = [expense];
  env.run('expenseTable(byId("expenses-list"), payload, "Dépenses")');
  assert.match(env.get('expenses-list').text, /42,50/);
  assert.match(env.get('expenses-list').text, /<img src=x onerror=alert\(1\)>/);
  assert.equal(env.run('money(null)'), 'Non disponible');
});

test('ne déduit jamais le verdict et conserve les preuves divergentes', () => {
  const env = setup();
  env.context.payload = { python: result, sql: { ...result, expense_ids: [2] }, verdict: 'divergence', expenses: [expense] };
  env.run('renderCalculation(payload)');
  assert.match(env.get('verdict').text, /Divergence/);
  assert.match(env.get('python-result').text, /identifiants\) : 1/);
  assert.match(env.get('sql-result').text, /identifiants\) : 2/);
  assert.match(env.get('sql-result').text, /pas fourni/);
  env.context.payload = { python: result, sql: result };
  env.run('renderCalculation(payload)');
  assert.match(env.get('verdict').text, /non validé/);
  env.context.payload.verdict = 'concordance';
  env.run('renderCalculation(payload)');
  assert.match(env.get('verdict').text, /Concordance confirmée par le backend/);
});

test('erreurs HTTP, JSON, réseau et outil sans résultat numérique inventé', async () => {
  const env = setup();
  for (const [response, expected] of [
    [{ http: 422 }, /Fichier invalide/], [{ http: 500 }, /Erreur serveur/],
    [{ http: 404 }, /Ressource introuvable/], [{ invalidJson: true }, /JSON invalide/],
    [new TypeError('network'), /Backend injoignable/],
    [{ ok: false, error: { message: 'Import refusé' } }, /Import refusé/],
  ]) {
    env.routes.set('/imports', response);
    await assert.rejects(env.run('api("/imports")'), expected);
  }
  env.context.payload = { ok: false, error: { message: 'Calcul impossible' } };
  env.run('renderTool("python-result", payload)');
  assert.equal(env.get('python-result').text, 'Calcul impossible');
});

test('question envoyée intacte, précision puis consultation du détail', async () => {
  const env = setup();
  const form = env.get('chat-form');
  env.get('question').value = 'Combien ai-je dépensé récemment ?';
  env.routes.set('/chat', { status: 'needs_clarification', message: 'Veuillez préciser la période.' });
  await form.listeners.submit({ preventDefault() {}, currentTarget: form });
  assert.equal(JSON.parse(env.calls.find((call) => call.path === '/chat').options.body).question, env.get('question').value);
  assert.equal(env.get('chat-status').text, 'Veuillez préciser la période.');
  assert.equal(env.get('results').hidden, true);
  env.routes.set('/chat', { calculation_id: 12 });
  env.routes.set('/calculations/12', { python: result, sql: result, verdict: 'concordance' });
  await form.listeners.submit({ preventDefault() {}, currentTarget: form });
  assert.ok(env.calls.some((call) => call.path === '/calculations/12'));
  assert.equal(env.get('results').hidden, false);
  assert.equal(form.querySelector().disabled, false);
});

test('import multipart puis rechargement des dépenses', async () => {
  const env = setup();
  await new Promise(setImmediate);
  const file = new Blob(['date,description,categorie,montant\n']);
  file.name = 'depenses.csv';
  env.get('csv-file').files = [file];
  env.routes.set('/imports', { imported_count: 0 });
  const form = env.get('import-form');
  await form.listeners.submit({ preventDefault() {}, currentTarget: form });
  const call = env.calls.find((call) => call.path === '/imports');
  assert.equal(call.options.method, 'POST');
  assert.ok(call.options.body.get('file') instanceof Blob);
  assert.equal(call.options.headers, undefined);
  assert.match(env.get('import-status').text, /Import réussi/);
  assert.equal(env.calls.at(-1).path, '/expenses');
});

const trace = {
  tool: 'verify_expenses',
  arguments: { operation: 'total_by_category', category: 'Alimentation', start_date: null, end_date: null, count: 0, enabled: false },
  status: 'success', result: { verdict: 'concordance', result_cents: 7250 },
};

test('trace backend : outil, tous les arguments, null, statut et résultat', () => {
  const env = setup();
  env.context.payload = { tool_trace: [trace], python: result, sql: result };
  env.run('renderCalculation(payload)');
  assert.equal(env.get('tool-trace').hidden, false);
  const text = env.get('tool-trace-list').text;
  for (const expected of ['Appel 1', 'Outil : verify_expenses', 'operation : total_by_category',
    'category : Alimentation', 'start_date : null', 'end_date : null', 'count : 0', 'enabled : false',
    'Statut : succès', 'Verdict : concordance', 'Montant : 72,50']) assert.ok(text.includes(expected), expected);
  assert.match(env.get('python-result').text, /42,50/);
});

test('plusieurs appels, erreur rouge sans montant même si un résultat est présent', () => {
  const env = setup();
  env.context.payload = [trace, { ...trace, tool: 'autre_outil', status: 'error',
    error: { code: 'tool_error', message: "Le calcul n'a pas pu être validé." } }];
  env.run('renderToolTrace(payload)');
  const blocks = env.get('tool-trace-list').children;
  assert.equal(blocks.length, 2);
  assert.match(blocks[1].text, /Appel 2.*autre_outil.*Statut : erreur.*tool_error.*Le calcul n'a pas pu être validé/);
  assert.doesNotMatch(blocks[1].text, /72,50|Montant|concordance/);
  assert.ok(blocks[1].children.some((child) => child.className === 'error'));
});

test('noms, clés, valeurs, résultats et erreurs sont insérés comme texte', () => {
  const env = setup();
  const attack = '<script>alert(1)</script>';
  env.context.payload = [{ tool: attack, arguments: { [attack]: attack }, status: 'success', result: { verdict: attack, extra: attack } },
    { tool: attack, arguments: {}, status: 'error', error: { code: attack, message: attack } }];
  env.run('renderToolTrace(payload)');
  const visit = (node) => {
    assert.equal(Object.hasOwn(node, 'innerHTML'), false);
    node.children.forEach(visit);
  };
  visit(env.get('tool-trace-list'));
  assert.equal(env.get('tool-trace-list').text.split(attack).length - 1, 8);
});

test('trace absente, vide ou invalide : aucune trace inventée ou conservée', () => {
  const env = setup();
  for (const missing of [undefined, null, [], {}, 'invalid']) {
    env.context.payload = [trace];
    env.run('renderToolTrace(payload)');
    env.context.payload = { python: result, sql: result, verdict: 'concordance', tool_trace: missing };
    env.run('renderCalculation(payload)');
    assert.equal(env.get('tool-trace').hidden, true);
    assert.equal(env.get('tool-trace-list').children.length, 0);
  }
  env.run('renderToolTrace([null, {status: "unknown"}])');
  assert.doesNotMatch(env.get('tool-trace-list').text, /succès|Montant/);
});

test('la trace du détail HTTP est effacée à la question suivante même en erreur', async () => {
  const env = setup();
  env.get('question').value = 'Total ?';
  env.routes.set('/chat', { calculation_id: 12 });
  env.routes.set('/calculations/12', { tool_trace: [trace] });
  const form = env.get('chat-form');
  await form.listeners.submit({ preventDefault() {}, currentTarget: form });
  assert.equal(env.get('tool-trace').hidden, false);
  env.routes.set('/chat', { http: 502 });
  await form.listeners.submit({ preventDefault() {}, currentTarget: form });
  assert.equal(env.get('tool-trace').hidden, true);
  assert.equal(env.get('tool-trace-list').children.length, 0);
});
