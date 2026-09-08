const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() { this.children = []; this.textContent = ''; this.listeners = {}; this.disabled = false; }
  set innerHTML(value) { throw new Error("Unsafe HTML insertion"); }
  append(...children) { this.children.push(...children); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
  removeAttribute() {}
  addEventListener(event, callback) { this.listeners[event] = callback; }
  querySelector() { return this.button ??= new Element(); }
  focus() {}
  reset() {}
  get text() { return this.textContent + this.children.map((child) => child.text).join(' '); }
}
function setup(extraRoutes = []) {
  const elements = new Map();
  const get = (id) => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  const calls = [];
  const routes = new Map([
    ['/health', { status: 'ok' }], ['/expenses', { expenses: [] }],
    ...extraRoutes,
  ]);
  const context = vm.createContext({
    window: { addEventListener() {}, location: { hash: "" } },
    document: { getElementById: get, createElement: () => new Element() },
    TextDecoder, Intl, AbortController, setTimeout, clearTimeout, FormData, TypeError,
    fetch: async (path, options) => {
      calls.push({ path, options });
      let data = routes.get(path);
      if (typeof data === 'function') data = await data(path, options);
      if (data instanceof Error) throw data;
      if (data?.body) return data;
      return { ok: !data?.http, status: data?.http ?? 200,
        json: async () => { if (data?.invalidJson) throw new Error(); return data; } };
    },
  });
  vm.runInContext(fs.readFileSync('static/js/stream.js', 'utf8'), context);
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

test('contrôle agent : état réel, actions adaptées et journal sûr du plus récent au plus ancien', async () => {
  let agentState = 'active';
  const attack = '<script>window.agentLogExecuted = true</script>';
  const logs = [
    { timestamp: '2026-09-08T08:00:00Z', message: 'Agent démarré.', api_key: 'secret-ignored' },
    { timestamp: '2026-09-08T10:30:00Z', message: attack },
  ];
  const env = setup([
    ['/agent/status', () => ({ status: agentState })],
    ['/agent/logs', () => ({ logs })],
    ['/agent/stop', (_path, options) => {
      assert.equal(options.method, 'POST');
      agentState = 'stopped';
      logs.push({ timestamp: '2026-09-08T11:00:00Z', message: 'Agent arrêté.' });
      return { status: agentState };
    }],
    ['/agent/restart', (_path, options) => {
      assert.equal(options.method, 'POST');
      agentState = 'active';
      return { status: agentState };
    }],
  ]);
  await new Promise(setImmediate);

  assert.equal(env.get('agent-state').text, 'Agent actif');
  assert.equal(env.get('agent-stop').disabled, false);
  assert.equal(env.get('agent-restart').disabled, true);
  assert.ok(env.get('agent-log').text.indexOf(attack) < env.get('agent-log').text.indexOf('Agent démarré.'));
  assert.doesNotMatch(env.get('agent-log').text, /secret-ignored/);
  assert.equal(env.get('agent-log').children[0].children[1].text, attack);

  await env.get('agent-stop').listeners.click();
  assert.equal(env.get('agent-state').text, 'Agent arrêté');
  assert.equal(env.get('agent-stop').disabled, true);
  assert.equal(env.get('agent-restart').disabled, false);
  assert.match(env.get('agent-control-message').text, /Agent arrêté.*actualisés/);
  assert.equal(env.get('agent-control-message').className, 'success');
  assert.equal(env.get('agent-log').children[0].children[1].text, 'Agent arrêté.');
  assert.ok(env.calls.filter((call) => call.path === '/agent/status').length >= 2);
  assert.ok(env.calls.filter((call) => call.path === '/agent/logs').length >= 2);
});

test('contrôle agent : 404/503 et formats invalides ne fabriquent aucun état', async () => {
  for (const response of [{ http: 404 }, { http: 503 }, { status: 'starting' }]) {
    const env = setup([
      ['/agent/status', response],
      ['/agent/logs', response.http ? response : { logs: [] }],
    ]);
    await new Promise(setImmediate);
    assert.equal(env.get('agent-state').text, 'Contrôle indisponible');
    assert.equal(env.get('agent-stop').disabled, true);
    assert.equal(env.get('agent-restart').disabled, true);
    assert.match(env.get('agent-control-message').text, response.http ? /Contrôle indisponible/ : /État de l’agent invalide/);
    assert.equal(env.get('agent-control-message').className, 'error');
  }
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

const sse = (type, payload) => `event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`;
function streamResponse(body) {
  return { ok: true, headers: new Headers({ 'Content-Type': 'text/event-stream; charset=utf-8' }), body };
}

test('SSE reconstruit les lignes, CRLF, commentaires et données multilignes à chaque coupure', () => {
  const env = setup();
  const source = ': heartbeat\r\nevent: agent\r\ndata: {\r\ndata: "message":"Analyse é €"}\r\n\r\nevent: final\ndata: {"answer":"Fini"}\n\n';
  for (let split = 0; split <= source.length; split++) {
    const events = [];
    env.context.receive = (type, data) => events.push([type, JSON.parse(data)]);
    const parser = env.run('createSSEParser(receive)');
    parser.push(source.slice(0, split));
    parser.push(source.slice(split));
    parser.end();
    assert.deepEqual(events, [['agent', { message: 'Analyse é €' }], ['final', { answer: 'Fini' }]]);
  }
  const events = [];
  env.context.receive = (...args) => events.push(args);
  const parser = env.run('createSSEParser(receive)');
  parser.push('event: final\ndata: {"answer":"Incomplet"}');
  parser.end();
  assert.equal(events.length, 0);
});

test('événements rendus immédiatement, résultat dans le même bloc et textes sûrs', () => {
  const env = setup();
  const attack = '<script>alert(1)</script>';
  env.context.payload = { message: attack };
  env.run('handleStreamEvent("agent", payload)');
  assert.equal(env.get('live-execution').hidden, false);
  assert.equal(env.get('live-events').text, attack);
  env.context.payload = { ...trace, tool: attack, arguments: { ...trace.arguments, [attack]: attack } };
  env.run('handleStreamEvent("tool_call", payload)');
  const block = env.get('live-events').children[1];
  for (const text of [attack, 'operation : total_by_category', 'category : Alimentation', 'start_date : null', 'end_date : null', 'count : 0', 'enabled : false']) assert.ok(block.text.includes(text));
  assert.doesNotMatch(block.text, /succès|Montant/);
  env.context.payload = { tool: attack, status: 'success', result: { verdict: attack, result_cents: 7250 } };
  env.run('handleStreamEvent("tool_result", payload)');
  assert.equal(env.get('live-events').children[1], block);
  assert.match(block.text, /Statut : succès.*Montant : 72,50/);
  env.context.payload = { answer: attack };
  env.run('handleStreamEvent("final", payload)');
  assert.ok(env.get('live-events').text.includes(`Réponse finale : ${attack}`));
  assert.equal(env.get('live-events').children.length, 3);
  assert.doesNotMatch(fs.readFileSync('static/js/stream.js', 'utf8'), /innerHTML|setTimeout/);
});

test('erreurs avant la fin et résultat orphelin ne fabriquent aucun appel', () => {
  const env = setup();
  env.context.payload = { message: '<img src=x onerror=alert(1)>' };
  env.run('handleStreamEvent("error", payload)');
  assert.equal(env.get('live-events').children[0].className, 'error');
  env.context.payload = trace;
  assert.throws(() => env.run('handleStreamEvent("tool_result", payload)'), /sans appel/);
  assert.equal(env.get('live-events').children.length, 1);
  env.run('handleStreamEvent("tool_call", payload)');
  env.context.payload = { ...trace, status: 'error', error: { code: 'tool_error', message: 'Échec <script>x</script>' } };
  env.run('handleStreamEvent("tool_result", payload)');
  const block = env.get('live-events').children[1];
  assert.match(block.text, /Statut : erreur.*tool_error.*Échec <script>x<\/script>/);
  assert.doesNotMatch(block.text, /Montant|72,50|concordance/);
});

test('appels concurrents identifiés : résultats hors ordre, aucun rattachement ambigu', () => {
  const env = setup();
  for (const call_id of ['a', 'b']) {
    env.context.payload = { ...trace, call_id };
    env.run('handleStreamEvent("tool_call", payload)');
  }
  env.context.payload = { ...trace, call_id: 'b' };
  env.run('handleStreamEvent("tool_result", payload)');
  assert.doesNotMatch(env.get('live-events').children[0].text, /Montant/);
  assert.match(env.get('live-events').children[1].text, /72,50/);
  env.run('resetStream()');
  env.context.payload = trace;
  env.run('handleStreamEvent("tool_call", payload); handleStreamEvent("tool_call", payload)');
  assert.throws(() => env.run('handleStreamEvent("tool_result", payload)'), /unique/);
});

test('fetch progressif : rendu avant fermeture, UTF-8 coupé octet par octet, POST optionnel', async () => {
  const env = setup();
  let source;
  const body = new ReadableStream({ start(controller) { source = controller; } });
  env.routes.set('/chat/stream', streamResponse(body));
  env.get('stream-mode').checked = true;
  env.get('question').value = 'Combien en alimentation ?';
  const form = env.get('chat-form');
  const pending = form.listeners.submit({ preventDefault() {}, currentTarget: form });
  const encoder = new TextEncoder();
  source.enqueue(encoder.encode(sse('agent', { message: 'Analyse en cours' })));
  await new Promise(setImmediate);
  assert.match(env.get('live-events').text, /Analyse en cours/);
  assert.equal(form.querySelector().disabled, true);
  source.enqueue(encoder.encode(sse('tool_call', trace)));
  await new Promise(setImmediate);
  assert.match(env.get('live-events').text, /verify_expenses/);
  assert.doesNotMatch(env.get('live-events').text, /Montant/);
  const rest = sse('tool_result', trace) + sse('final', { answer: 'Dépensé : 72,50 €' });
  for (const byte of encoder.encode(rest)) source.enqueue(Uint8Array.of(byte));
  await pending;
  assert.match(env.get('live-events').text, /Réponse finale : Dépensé : 72,50 €/);
  assert.equal(form.querySelector().disabled, false);
  assert.equal(body.locked, false);
  assert.equal(env.get('stream-cancel').hidden, true);
  const call = env.calls.find((item) => item.path === '/chat/stream');
  assert.equal(call.options.method, 'POST');
  assert.equal(call.options.headers.Accept, 'text/event-stream');
  assert.equal(JSON.parse(call.options.body).question, env.get('question').value);
  assert.ok(!env.calls.some((item) => item.path === '/chat'));
});

test('flux invalide, HTTP indisponible, EOF prématurée et erreur terminale sont signalés', async () => {
  for (const [wire, expected] of [
    ['', /interrompu/], ['event: final\ndata: {bad}\n\n', /JSON invalide/],
    [sse('error', { message: 'Erreur serveur' }) + sse('final', { answer: 'Ignoré' }), /Erreur serveur/],
    [sse('tool_result', trace), /sans appel/],
  ]) {
    const env = setup();
    const body = new ReadableStream({ start(source) { source.enqueue(new TextEncoder().encode(wire)); source.close(); } });
    env.routes.set('/chat/stream', streamResponse(body));
    await env.run('streamQuestion("question")');
    assert.match(env.get('chat-status').text, expected);
    assert.equal(env.get('chat-status').className, 'error');
    assert.doesNotMatch(env.get('live-events').text, /Outil :|Ignoré/);
  }
  const env = setup();
  env.routes.set('/chat/stream', { http: 404 });
  await env.run('streamQuestion("question")');
  assert.match(env.get('chat-status').text, /HTTP 404/);
  assert.ok(!env.calls.some((call) => call.path === '/chat'));
  env.routes.set('/chat/stream', { ...streamResponse(new ReadableStream()), headers: new Headers({ 'Content-Type': 'application/json' }) });
  await env.run('streamQuestion("question")');
  assert.match(env.get('chat-status').text, /pas fourni de flux SSE/);
});

test('carte réponse : synthèse serveur, masquée en divergence et sans données', () => {
  const env = setup();
  env.context.payload = { answer: '<script>texte</script>', verdict: 'concordance', python: result, sql: result,
    request: { category: 'Alimentation' } };
  env.run('renderCalculation(payload)');
  assert.equal(env.get('answer-card').hidden, false);
  assert.equal(env.get('answer').text, '<script>texte</script>');
  assert.equal(env.get('summary-count').text, '1');
  assert.equal(env.get('summary-category').text, 'Alimentation');
  assert.match(env.get('summary-amount').text, /42,50/);
  assert.equal(env.get('answer-summary').hidden, false);
  env.context.payload.verdict = 'divergence';
  env.run('renderCalculation(payload)');
  assert.equal(env.get('answer-summary').hidden, true);
  assert.match(env.get('answer-verdict').text, /non validé/);
  env.context.payload = { answer: 'Réponse du flux' };
  env.run('resetAnalysis(); renderAnswer(payload)');
  assert.equal(env.get('answer-summary').hidden, true);
  assert.equal(env.get('answer-details').hidden, true);
  assert.equal(env.get('answer').text, 'Réponse du flux');
});

test('recherche et catégorie filtrent la liste sans modifier les résultats', async () => {
  const env = setup();
  await new Promise(setImmediate);
  env.routes.set('/expenses', { expenses: [expense, { ...expense, id: 2, category: 'Transport', description: 'Train' }] });
  await env.run('refreshExpenses()');
  assert.equal(env.get('expenses-count').text, '(2 / 2)');
  env.get('expense-search').value = 'TRAIN';
  env.get('expense-search').listeners.input();
  assert.match(env.get('expenses-list').text, /Train/);
  assert.doesNotMatch(env.get('expenses-list').text, /Alimentation/);
  env.get('category-filter').value = 'Alimentation';
  env.get('category-filter').listeners.change();
  assert.equal(env.get('expenses-count').text, '(0 / 2)');
  env.get('expense-search').value = '';
  env.get('expense-search').listeners.input();
  assert.equal(env.get('expenses-count').text, '(1 / 2)');
  assert.match(env.get('expenses-list').text, /<img src=x/);
});

test('dépôt CSV : sélection explicite sans envoi et refus des autres formats', () => {
  const env = setup();
  const files = [{ name: '<script>depenses</script>.csv' }];
  env.get('drop-zone').listeners.drop({ preventDefault() {}, dataTransfer: { files } });
  assert.equal(env.get('csv-file').files, files);
  assert.equal(env.get('file-name').text, files[0].name);
  assert.ok(!env.calls.some((call) => call.path === '/imports'));
  env.get('drop-zone').listeners.drop({ preventDefault() {}, dataTransfer: { files: [{ name: 'bad.xlsx' }] } });
  assert.match(env.get('import-status').text, /un seul fichier CSV/);
  assert.equal(env.get('csv-file').files, files);
});

test('final complet du flux affiche comparaison et synthèse sans dupliquer la trace', () => {
  const env = setup();
  env.context.payload = trace;
  env.run('handleStreamEvent("tool_call", payload); handleStreamEvent("tool_result", payload)');
  const block = env.get('live-events').children[0];
  env.context.payload = { answer: 'Réponse vérifiée', verdict: 'concordance', python: result, sql: result,
    request: { category: 'Alimentation' }, tool_trace: [trace] };
  env.run('handleStreamEvent("final", payload)');
  assert.equal(env.get('results').hidden, false);
  assert.equal(env.get('answer-summary').hidden, false);
  assert.equal(env.get('answer').text, 'Réponse vérifiée');
  assert.match(env.get('python-amount').text, /42,50/);
  assert.equal(env.get('live-events').children[0], block);
  assert.equal(env.get('tool-trace-list').children.length, 0);
});
