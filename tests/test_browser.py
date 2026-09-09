"""Real browser -> Flask -> installed Anthropic SDK -> both SQLite calculators.

The happy path replaces only Anthropic HTTP. The trace contract test uses
an explicit Flask response fixture until the agent backend supplies tool_trace.
"""
from threading import Thread

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from conftest import CSV_CONTENT


def test_browser_happy_path(application, claude, monkeypatch):
    claude["arguments"]["category"] = "alimentation"
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#request-info-toggle")).to_be_disabled()
            expect(page.locator("#request-info")).to_be_hidden()
            expect(page.locator("#agent-trace")).not_to_have_attribute("open", "")
            page.locator("#agent-trace > summary").click()
            expect(page.locator("#health-status")).to_have_text("Backend disponible.")
            page.locator("#csv-file").set_input_files({"name": "expenses.csv", "mimeType": "text/csv", "buffer": CSV_CONTENT})
            page.get_by_role("button", name="Importer", exact=True).click()
            expect(page.locator("#import-status")).to_have_text("Import réussi.")
            expect(page.locator("#expenses-list tbody tr")).to_have_count(4)
            page.locator("#question").fill("Combien ai-je dépensé en alimentation ?")
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#answer")).to_contain_text("72,50 €")
            expect(page.locator("#request-info")).to_be_hidden()
            page.get_by_role("button", name="Infos requête").click()
            expect(page.locator("#request-info")).to_be_visible()
            expect(page.locator("#verdict")).to_have_text("Concordance confirmée par le backend.")
            expect(page.locator("#answer-card")).to_be_visible()
            expect(page.locator("#summary-count")).to_have_text("3")
            expect(page.locator("#summary-amount")).to_contain_text("72,50")
            expect(page.locator("#request-cost")).to_have_text("0.00044000 USD")
            expect(page.locator("#request-confidence")).to_have_text("Confiance élevée")
            expect(page.locator("#request-model-calls")).to_have_text("2")
            expect(page.locator("#request-tool-calls")).to_have_text("1")
            expect(page.locator("#request-calls")).to_have_text("3")
            expect(page.locator("#request-input-tokens")).to_have_text("20")
            expect(page.locator("#request-output-tokens")).to_have_text("40")
            expect(page.locator("#request-total-tokens")).to_have_text("60")
            page.set_viewport_size({"width": 1360, "height": 1000})
            page.screenshot(path="/tmp/le-sosie-desktop.png", full_page=True)
            page.locator("#expense-search").fill("Carrefour")
            expect(page.locator("#expenses-list tbody tr")).to_have_count(1)
            page.locator("#expense-search").fill("")
            page.locator("#category-filter").select_option("Transport")
            expect(page.locator("#expenses-list tbody tr")).to_have_count(1)
            page.locator("#category-filter").select_option("")
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path="/tmp/le-sosie-mobile.png", full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("#calculation-details").evaluate("element => element.open = true")
            for name in ("python", "sql"):
                expect(page.locator(f"#{name}-result")).to_contain_text("72,50")
                expect(page.locator(f"#{name}-result tbody tr")).to_have_count(3)
            expect(page.locator("#total-duration")).not_to_contain_text("Non disponible")
            # The agent really called verify_expenses for this question: the
            # trace section now shows that one successful call.
            trace = page.locator("#tool-trace")
            expect(trace).to_be_visible()
            expect(trace).to_contain_text("verify_expenses")
            expect(trace).to_contain_text("Statut : succès")
            expect(trace.locator("article")).to_have_count(1)
            # The real SSE endpoint must finish with the same verified dashboard.
            page.locator("#stream-mode").check()
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#results")).to_be_visible()
            expect(page.locator("#answer")).to_contain_text("72,50 € dans la catégorie alimentation")
            expect(page.locator("#summary-count")).to_have_text("3")
            expect(page.locator("#python-amount")).to_contain_text("72,50")
            expect(page.locator("#sql-amount")).to_contain_text("72,50")
            expect(page.locator("#request-cost")).to_have_text("0.00044000 USD")
            expect(page.locator("#live-events article")).to_have_count(1)
            expect(page.locator("#tool-trace")).to_be_hidden()
            page.locator("#agent-trace > summary").click()
            expect(page.locator("#live-events")).to_be_hidden()
            page.locator("#agent-trace > summary").click()
            expect(page.locator("#live-events")).to_be_visible()
            page.locator("#stream-mode").uncheck()
            claude["tool_call"] = False
            claude["final_text"] = "Veuillez préciser la période."
            page.locator("#question").fill("Combien ai-je dépensé récemment ?")
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#chat-status")).to_have_text("Veuillez préciser la période.")
            expect(page.locator("#request-cost")).to_have_text("0.00022000 USD")
            expect(page.locator("#results")).to_be_hidden()
            # Vrais endpoints et boucle SDK ; seule la réponse Anthropic est simulée.
            for streaming in (False, True):
                page.locator("#stream-mode").set_checked(streaming)
                for response_status, label, confidence in (
                    ("needs_clarification", "Demande de précision", "Incertitude / information insuffisante"),
                    ("security_refusal", "Refus de sécurité", "Refus"),
                    ("refused", "Refus", "Refus"),
                ):
                    claude["response_status"] = response_status
                    page.get_by_role("button", name="Analyser").click()
                    expect(page.get_by_role("button", name="Analyser")).to_be_enabled()
                    expect(page.locator("#request-outcome")).to_contain_text(label)
                    expect(page.locator("#request-confidence")).to_have_text(confidence)
                    expect(page.locator("#request-cost")).to_have_text("0.00022000 USD")
                    expect(page.locator("#request-tool-calls")).to_have_text("0")
                    expect(page.locator("#request-total-tokens")).to_have_text("30")
                    expect(page.locator("#results")).to_be_hidden()
                    expect(page.locator("#answer-summary")).to_be_hidden()
            page.locator("#stream-mode").uncheck()
            monkeypatch.delenv("ANTHROPIC_API_KEY")
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#chat-status")).to_contain_text("ANTHROPIC_API_KEY")
            expect(page.locator("#request-cost")).to_have_text("0.00000000 USD")
            expect(page.locator("#request-outcome")).to_contain_text("Erreur technique")
            expect(page.locator("#request-confidence")).to_have_text("Erreur")
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_browser_agent_control_uses_backend_responses(application):
    """The panel reflects API responses and never interprets log text as HTML."""
    import json
    from urllib.parse import urlparse

    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            agent = {"status": "running", "reason": None}
            log_message = "<script>window.agentLogExecuted = true</script>"

            def agent_api(route):
                if urlparse(route.request.url).path != "/agent/state":
                    route.fulfill(status=404, content_type="application/json", body='{"error":{"message":"Absent"}}')
                    return
                if route.request.method == "POST":
                    payload = json.loads(route.request.post_data)
                    agent["status"] = payload["status"]
                    agent["reason"] = "arret manuel" if payload["status"] == "stopped" else None
                route.fulfill(status=200, content_type="application/json", body=json.dumps(agent))

            page.route("**/agent/state", agent_api)
            page.route(
                "**/agent/logs*",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({
                        "logs": [{
                            "timestamp": "2026-09-08T10:30:00.000Z",
                            "level": "INFO",
                            "message": log_message,
                        }],
                        "count": 1,
                    }),
                ),
            )
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#agent-state")).to_have_text("Agent actif")
            expect(page.locator("#agent-stop")).to_be_enabled()
            expect(page.locator("#agent-restart")).to_be_disabled()
            expect(page.locator("#agent-log")).to_contain_text(log_message)
            assert page.evaluate("window.agentLogExecuted") is None

            page.locator("#agent-stop").click()
            expect(page.locator("#agent-state")).to_have_text("Agent arrêté")
            expect(page.locator("#agent-stop")).to_be_disabled()
            expect(page.locator("#agent-restart")).to_be_enabled()
            expect(page.locator("#agent-control-message")).to_contain_text("Agent arrêté")
            expect(page.locator("#agent-log")).to_contain_text(log_message)
            page.locator("#agent-restart").click()
            expect(page.locator("#agent-state")).to_have_text("Agent actif")
            expect(page.locator("#agent-stop")).to_be_enabled()
            expect(page.locator("#agent-restart")).to_be_disabled()
            expect(page.locator("#agent-control-message")).to_contain_text("Agent redémarré")
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_browser_tool_trace_contract(application, monkeypatch):
    """HTTP contract fixture only: this does not exercise agent tool calling."""
    from flask import jsonify

    attack = "<script>window.traceExecuted = true</script>"
    trace = [{
        "tool": "verify_expenses",
        "arguments": {"operation": "total_by_category", "category": "Alimentation",
                      "start_date": None, "end_date": None, "note": attack},
        "status": "success",
        "result": {"verdict": "concordance", "result_cents": 7250, "note": attack},
    }, {
        "tool": attack, "arguments": {attack: attack}, "status": "error",
        "error": {"code": "tool_error", "message": "Le calcul n'a pas pu être validé. " + attack},
        "result": {"result_cents": 99999},
    }]
    # The server supplies an explicit fixture, never reconstructed from calculators.
    monkeypatch.setitem(application.view_functions, "api.chat", lambda: jsonify({"calculation_id": 12}))
    monkeypatch.setitem(application.view_functions, "api.get_calculation", lambda calculation_id: jsonify({
        "answer": "Réponse de la fixture HTTP.", "verdict": "concordance", "tool_trace": trace,
    }))
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#agent-trace")).not_to_have_attribute("open", "")
            page.locator("#agent-trace > summary").click()
            section = page.locator("#tool-trace")
            expect(section).to_be_hidden()
            page.locator("#question").fill("Combien ai-je dépensé en alimentation ?")
            page.get_by_role("button", name="Analyser").click()
            expect(section).to_be_visible()
            for text in ("verify_expenses", "total_by_category", "Alimentation",
                         "concordance", "72,50", "start_date : null", "end_date : null", attack):
                expect(section).to_contain_text(text)
            expect(section.locator("article")).to_have_count(2)
            failure = section.locator("article").nth(1)
            expect(failure.locator("div.error")).to_contain_text("Le calcul n'a pas pu être validé.")
            expect(failure).to_contain_text("Statut : erreur")
            expect(failure).not_to_contain_text("999,99")
            expect(section.locator("script")).to_have_count(0)
            assert page.evaluate("window.traceExecuted === undefined")
            trace.clear()
            page.get_by_role("button", name="Analyser").click()
            expect(section).to_be_hidden()
            expect(section.locator("article")).to_have_count(0)
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_browser_progressive_sse(application, monkeypatch):
    """A real HTTP stream gated by assertions, with no timer/typewriter effect."""
    import json
    from threading import Event
    from flask import Response

    continue_stream = Event()

    def stream_fixture():
        def events():
            yield 'event: agent\ndata: {"message":"Analyse reçue du serveur"}\n\n'
            # The test releases the remaining events only after seeing this text.
            if not continue_stream.wait(timeout=15):
                return
            call = {"tool": "verify_expenses", "arguments": {"category": None}}
            yield f'event: tool_call\ndata: {json.dumps(call)}\n\n'
            result = {"tool": "verify_expenses", "status": "success", "result": {"result_cents": 7250}}
            yield f'event: tool_result\ndata: {json.dumps(result)}\n\n'
            yield 'event: final\ndata: {"answer":"Réponse du serveur : 72,50 €"}\n\n'
        return Response(events(), content_type="text/event-stream; charset=utf-8")

    # Patch the real endpoint's view function rather than registering a
    # second rule for the same path: the agent backend now really owns
    # POST /chat/stream, and Flask/Werkzeug would silently keep whichever
    # rule was registered first, ignoring an added duplicate route.
    monkeypatch.setitem(application.view_functions, "api.chat_stream", stream_fixture)

    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#agent-trace")).not_to_have_attribute("open", "")
            page.locator("#agent-trace > summary").click()
            page.locator("#stream-mode").check()
            page.locator("#question").fill("Total ?")
            submit = page.get_by_role("button", name="Analyser")
            submit.click()
            live = page.locator("#live-execution")
            expect(live).to_contain_text("Analyse reçue du serveur")
            expect(submit).to_be_disabled()
            expect(live.locator("article")).to_have_count(0)
            continue_stream.set()
            expect(live).to_contain_text("Réponse du serveur : 72,50 €")
            expect(live.locator("article")).to_have_count(1)
            expect(live.locator("article")).to_contain_text("category : null")
            expect(live.locator("article")).to_contain_text("Statut : succès")
            expect(live.locator("article")).to_contain_text("72,50")
            expect(submit).to_be_enabled()
            assert errors == []
            browser.close()
    finally:
        continue_stream.set()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_browser_operation_toggle(application, claude, monkeypatch):
    """The test-mode panel really disables an operation end to end: the agent
    still calls the tool, but the backend refuses it and no amount is shown."""
    import app.test_controls as test_controls
    monkeypatch.setenv("ENABLE_TEST_CONTROLS", "1")
    monkeypatch.setattr(test_controls, "_disabled_operations", set())
    claude["arguments"]["category"] = "alimentation"
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}")
            panel = page.locator("#test-operations")
            expect(panel).to_be_visible()
            toggle = panel.locator("label", has_text="Total par catégorie").locator("input")
            expect(toggle).to_be_checked()
            toggle.uncheck()
            expect(page.locator("#test-operations-status")).to_contain_text("désactivée")

            page.locator("#question").fill("Combien ai-je dépensé en alimentation ?")
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#verdict")).to_contain_text("Divergence")
            expect(page.locator("#answer")).not_to_contain_text("€")
            page.locator("#agent-trace summary").click()  # the trace card is collapsed by default
            trace = page.locator("#tool-trace")
            expect(trace).to_be_visible()
            expect(trace).to_contain_text("operation_disabled")
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


# Palier 5 contract fixtures: these optional fields are not implemented by the backend yet.
def test_browser_request_info_http(application):
    _check_request_info_contract(application, streaming=False)


def test_browser_request_info_sse(application):
    _check_request_info_contract(application, streaming=True)


def _check_request_info_contract(application, streaming):
    import json

    attack = '<img src=x onerror="window.metricsExecuted=true"><script>window.metricsExecuted=true</script>'
    full = {
        "status": "verified", "confidence": "high",
        "metrics": {"total_duration_ms": 1234.56789, "calls": 7, "tool_calls": 2,
                    "model_calls": 4, "input_tokens": 100, "output_tokens": 20, "total_tokens": 150},
        "cost": {"amount": "0.00123000", "currency": "USD"},
    }
    metric_ids = ["request-duration", "request-calls", "request-tool-calls", "request-model-calls",
                  "request-input-tokens", "request-output-tokens", "request-total-tokens", "request-cost"]
    missing = ["Non disponible"] * len(metric_ids)
    cases = [
        ({"request_info": full}, "Réponse vérifiée", "Confiance élevée",
         ["1234.56789 ms", "7", "2", "4", "100", "20", "150", "0.00123000 USD"]),
        ({"request_info": {"confidence": "medium", "metrics": {"input_tokens": 0, "output_tokens": 20}}},
         "Non disponible", "Confiance moyenne", missing[:4] + ["0", "20"] + missing[6:]),
        ({}, "Non disponible", "Non disponible", missing),
        ({"verdict": "divergence", "request_info": {"confidence": "low"}},
         "Réponse non validée", "Confiance faible", missing),
        ({"status": "needs_clarification", "request_info": {"confidence": "uncertain"}},
         "Demande de précision", "Incertitude / information insuffisante", missing),
        ({"request_info": {**full, "status": "security_refusal"}}, "Refus de sécurité", "Refus",
         ["1234.56789 ms", "7", "2", "4", "100", "20", "150", "0.00123000 USD"]),
        ({"status": "refused"}, "Refus", "Refus", missing),
        ({"status": "error", "request_info": {"metrics": {"calls": 0}}},
         "Erreur technique", "Erreur", ["Non disponible", "0"] + missing[2:]),
        ({"request_info": {"confidence": attack, "status": attack, "metrics": {"input_tokens": attack},
                           "cost": {"amount": attack, "currency": attack},
                           "api_key": "private-key", "system_prompt": "private-prompt"}},
         "Non disponible", "Non disponible", missing),
        ({"request_info": {"confidence": "__proto__", "metrics": [], "cost": {"amount": 0.1, "currency": "EUR"}}},
         "Non disponible", "Non disponible", missing),
    ]
    response = {"payload": {}, "status": 200, "event": "final"}
    server = make_server("127.0.0.1", 0, application, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def reply(route):
                if streaming and response["status"] == 200:
                    body = f'event: {response["event"]}\ndata: {json.dumps(response["payload"])}\n\n'
                    route.fulfill(status=200, content_type="text/event-stream", body=body)
                else:
                    route.fulfill(status=response["status"], content_type="application/json",
                                  body=json.dumps(response["payload"]))

            page.route("**/chat/stream" if streaming else "**/chat", reply)
            page.goto(f"http://127.0.0.1:{server.server_port}")
            toggle = page.get_by_role("button", name="Infos requête")
            panel = page.locator("#request-info")
            expect(toggle).to_be_disabled()
            expect(toggle).to_have_attribute("aria-expanded", "false")
            expect(toggle).to_have_attribute("aria-controls", "request-info")
            expect(panel).to_be_hidden()
            expect(page.locator("#request-cost")).to_have_text("Non disponible")
            page.locator("#stream-mode").set_checked(streaming)
            page.locator("#question").fill("Total ?")
            for index, (payload, outcome, confidence, metrics) in enumerate(cases):
                response["payload"] = {"answer": attack, "message": attack, **payload}
                response["event"] = "error" if payload.get("status") == "error" else "final"
                page.get_by_role("button", name="Analyser").click()
                expect(page.get_by_role("button", name="Analyser")).to_be_enabled()
                if index == 0:
                    expect(panel).to_be_hidden()
                    expect(toggle).to_be_enabled()
                    toggle.focus()
                    page.keyboard.press("Enter")
                    expect(panel).to_be_visible()
                    expect(toggle).to_have_attribute("aria-expanded", "true")
                    expect(toggle).to_be_focused()
                    page.keyboard.press("Space")
                    expect(panel).to_be_hidden()
                    expect(toggle).to_have_attribute("aria-expanded", "false")
                    toggle.click()
                    expect(panel).to_be_visible()
                    # The control is in the question card, to the right of suggestions.
                    assert toggle.evaluate("el => el.closest('.question-card') !== null")
                    assert toggle.bounding_box()["x"] > page.locator("#suggest-total").bounding_box()["x"]
                elif index == 1:
                    # The second response arrived while the disclosure was closed.
                    expect(panel).to_be_hidden()
                    toggle.click()
                    expect(panel).to_be_visible()
                expect(page.locator("#request-outcome")).to_contain_text(outcome)
                expect(page.locator("#request-confidence")).to_have_text(confidence)
                for element_id, value in zip(metric_ids, metrics):
                    expect(page.locator(f"#{element_id}")).to_have_text(value)
                expect(page.locator("#request-info script, #request-info img, #answer script, #answer img")).to_have_count(0)
                expect(page.locator("#request-info")).not_to_contain_text("private-")
                assert page.evaluate("window.metricsExecuted === undefined")
                if index == 0:
                    expect(page.locator("#answer")).to_have_text(attack)
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    page.screenshot(path=f"/tmp/le-sosie-palier5-{'sse' if streaming else 'http'}.png", full_page=True)
                    toggle.click()
                    expect(panel).to_be_hidden()
                if outcome in ("Refus de sécurité", "Refus", "Demande de précision", "Erreur technique"):
                    expect(page.locator("#results")).to_be_hidden()
                    expect(page.locator("#answer-summary")).to_be_hidden()

            # Non-2xx metadata is retained for HTTP and the SSE handshake alike.
            response.update(status=403, payload={"ok": False, "error": {"message": attack},
                                                "request_info": {**full, "status": "security_refusal"}})
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#request-outcome")).to_contain_text("Refus de sécurité")
            expect(page.locator("#request-cost")).to_have_text("0.00123000 USD")
            expect(page.locator("#chat-status")).to_have_text(attack)
            expect(page.locator("#chat-status")).to_have_class("request-label refusal")
            response.update(status=500, payload={"error": {"message": "Erreur serveur"}})
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#request-outcome")).to_contain_text("Erreur technique")
            for element_id in metric_ids:
                expect(page.locator(f"#{element_id}")).to_have_text("Non disponible")
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
