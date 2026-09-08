"use strict";

// Incremental SSE framing only; JSON decoding and UI rendering live elsewhere.
function createSSEParser(onEvent) {
  let line = "", type = "", data = [], skipLF = false;
  function consumeLine() {
    if (line === "") {
      if (data.length) onEvent(type || "message", data.join("\n"));
      type = "";
      data = [];
    } else if (!line.startsWith(":")) {
      const colon = line.indexOf(":");
      const field = colon < 0 ? line : line.slice(0, colon);
      let value = colon < 0 ? "" : line.slice(colon + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") type = value;
      if (field === "data") data.push(value);
    }
    line = "";
  }
  return {
    push(text) {
      for (const char of text) {
        if (skipLF) { skipLF = false; if (char === "\n") continue; }
        if (char === "\r" || char === "\n") {
          consumeLine();
          skipLF = char === "\r";
        } else line += char;
      }
    },
    // SSE requires a blank line: never dispatch an unfinished event at EOF.
    end() { line = ""; type = ""; data = []; },
  };
}

let streamCalls = [];
let streamController = null;
function resetStream() {
  streamCalls = [];
  byId("live-events").replaceChildren();
  byId("live-execution").hidden = true;
}

function streamFields(parent, value, result = false) {
  const display = (item) => typeof item === "string" ? item : JSON.stringify(item);
  if (!isObject(value)) { paragraph(parent, display(value)); return; }
  for (const [key, item] of Object.entries(value)) {
    const label = result && key === "result_cents" ? "Montant" : key;
    paragraph(parent, `${label} : ${result && key === "result_cents" ? money(item) : display(item)}`);
  }
}

function handleStreamEvent(type, payload) {
  if (!["agent", "tool_call", "tool_result", "final", "error"].includes(type)) return;
  if (!isObject(payload)) throw new Error("Événement serveur invalide.");
  const list = byId("live-events");
  byId("live-execution").hidden = false;
  if (type === "agent" || type === "error" || type === "final") {
    const text = type === "final" ? payload.answer : payload.message;
    if (typeof text !== "string") throw new Error("Texte manquant dans l'événement serveur.");
    const entry = document.createElement("p");
    entry.textContent = type === "final" ? `Réponse finale : ${text}` : text;
    entry.className = type === "error" ? "error" : "";
    list.append(entry);
    return;
  }
  if (typeof payload.tool !== "string") throw new Error("Nom d'outil manquant dans le flux.");
  if (payload.call_id !== undefined && (typeof payload.call_id !== "string" || !payload.call_id)) {
    throw new Error("Identifiant d'appel invalide dans le flux.");
  }
  if (type === "tool_call") {
    if (!isObject(payload.arguments)) throw new Error("Arguments d'outil invalides dans le flux.");
    if (payload.call_id !== undefined && streamCalls.some((call) => call.id === payload.call_id)) {
      throw new Error("Identifiant d'appel dupliqué dans le flux.");
    }
    const block = document.createElement("article");
    block.className = "tool-trace-call";
    paragraph(block, `Outil : ${payload.tool}`);
    paragraph(block, "Arguments :");
    streamFields(block, payload.arguments);
    const output = document.createElement("div");
    block.append(output);
    list.append(block);
    streamCalls.push({ id: payload.call_id, tool: payload.tool, output, complete: false });
    return;
  }
  // Without an id, only an unambiguous pending call can be completed.
  const matches = streamCalls.filter((call) => !call.complete && call.tool === payload.tool
    && (payload.call_id === undefined ? call.id === undefined : call.id === payload.call_id));
  if (matches.length !== 1) throw new Error("Résultat reçu sans appel d'outil correspondant unique.");
  if (!["success", "error"].includes(payload.status)) throw new Error("Statut d'outil invalide dans le flux.");
  const call = matches[0];
  if (payload.status === "error") {
    call.output.className = "error";
    paragraph(call.output, "Statut : erreur");
    if (typeof payload.error?.code === "string") paragraph(call.output, `Code : ${payload.error.code}`);
    paragraph(call.output, typeof payload.error?.message === "string" ? payload.error.message : "Échec de l'outil.");
  } else {
    paragraph(call.output, "Statut : succès");
    paragraph(call.output, "Résultat :");
    if (Object.hasOwn(payload, "result")) streamFields(call.output, payload.result, true);
    else paragraph(call.output, "Résultat non disponible.");
  }
  call.complete = true;
}

async function streamQuestion(question) {
  const controller = new AbortController();
  streamController = controller;
  byId("stream-cancel").hidden = false;
  let reader;
  let terminal = false;
  try {
    const response = await fetch("/chat/stream", {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question }), signal: controller.signal,
    });
    if (!response.ok) throw new Error(`Flux indisponible (HTTP ${response.status}). Vous pouvez utiliser le parcours classique.`);
    if (response.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase() !== "text/event-stream"
        || !response.body) throw new Error("Le serveur n'a pas fourni de flux SSE.");
    reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: true });
    const parser = createSSEParser((type, data) => {
      if (terminal || !["agent", "tool_call", "tool_result", "final", "error"].includes(type)) return;
      let payload;
      try { payload = JSON.parse(data); }
      catch { throw new Error("JSON invalide dans le flux serveur."); }
      handleStreamEvent(type, payload);
      if (type === "final" || type === "error") {
        terminal = true;
        status("chat-status", type === "final" ? "Réponse reçue." : payload.message, type === "error" ? "error" : "");
      }
    });
    while (!terminal) {
      const { value, done } = await reader.read();
      if (done) { parser.push(decoder.decode()); parser.end(); break; }
      parser.push(decoder.decode(value, { stream: true }));
    }
    if (!terminal) throw new Error("Flux interrompu avant la réponse finale.");
  } catch (error) {
    const message = controller.signal.aborted ? "Lecture du flux annulée. L'exécution serveur peut continuer."
      : error instanceof TypeError ? "Flux illisible ou connexion interrompue." : error.message;
    // Transport diagnostics are not agent or tool events.
    status("chat-status", message, "error");
  } finally {
    if (reader) {
      try { await reader.cancel(); } catch { /* Connection may already be closed. */ }
      reader.releaseLock();
    }
    controller.abort();
    streamController = null;
    byId("stream-cancel").hidden = true;
  }
}
