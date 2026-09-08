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
            expect(page.locator("#verdict")).to_have_text("Concordance confirmée par le backend.")
            expect(page.locator("#answer-card")).to_be_visible()
            expect(page.locator("#summary-count")).to_have_text("3")
            expect(page.locator("#summary-amount")).to_contain_text("72,50")
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
            expect(page.locator("#results")).to_be_hidden()
            monkeypatch.delenv("ANTHROPIC_API_KEY")
            page.get_by_role("button", name="Analyser").click()
            expect(page.locator("#chat-status")).to_contain_text("ANTHROPIC_API_KEY")
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
            agent = {
                "status": "active",
                "logs": [
                    {"timestamp": "2026-09-08T08:00:00Z", "message": "Agent démarré."},
                    {"timestamp": "2026-09-08T10:30:00Z", "message": "<script>window.agentLogExecuted = true</script>"},
                ],
            }

            def agent_api(route):
                path = urlparse(route.request.url).path
                if path == "/agent/status":
                    payload = {"status": agent["status"]}
                elif path == "/agent/logs":
                    payload = {"logs": agent["logs"]}
                elif path == "/agent/stop" and route.request.method == "POST":
                    agent["status"] = "stopped"
                    agent["logs"].append({"timestamp": "2026-09-08T11:00:00Z", "message": "Agent arrêté."})
                    payload = {"status": agent["status"]}
                elif path == "/agent/restart" and route.request.method == "POST":
                    agent["status"] = "active"
                    payload = {"status": agent["status"]}
                else:
                    route.fulfill(status=404, content_type="application/json", body='{"error":{"message":"Absent"}}')
                    return
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            page.route("**/agent/**", agent_api)
            page.goto(f"http://127.0.0.1:{server.server_port}")
            expect(page.locator("#agent-state")).to_have_text("Agent actif")
            expect(page.locator("#agent-stop")).to_be_enabled()
            expect(page.locator("#agent-restart")).to_be_disabled()
            expect(page.locator("#agent-log article")).to_have_count(2)
            expect(page.locator("#agent-log article").first).to_contain_text("<script>window.agentLogExecuted")
            expect(page.locator("#agent-log script")).to_have_count(0)
            assert page.evaluate("window.agentLogExecuted === undefined")

            page.locator("#agent-stop").click()
            expect(page.locator("#agent-state")).to_have_text("Agent arrêté")
            expect(page.locator("#agent-stop")).to_be_disabled()
            expect(page.locator("#agent-restart")).to_be_enabled()
            expect(page.locator("#agent-control-message")).to_contain_text("État et journal actualisés")
            expect(page.locator("#agent-log article").first).to_contain_text("Agent arrêté.")
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
