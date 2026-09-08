"""Real browser -> Flask -> installed Anthropic SDK -> both SQLite calculators.

The happy path replaces only Anthropic HTTP. The trace contract test uses
an explicit Flask response fixture until the agent backend supplies tool_trace.
"""
from threading import Thread

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from conftest import CSV_CONTENT


def test_browser_happy_path(application, claude, monkeypatch):
    claude["parsed"]["category"] = "alimentation"
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
            expect(page.locator("#health-status")).to_have_text("Backend disponible.")
            page.locator("#csv-file").set_input_files({"name": "expenses.csv", "mimeType": "text/csv", "buffer": CSV_CONTENT})
            page.get_by_role("button", name="Importer", exact=True).click()
            expect(page.locator("#import-status")).to_have_text("Import réussi.")
            expect(page.locator("#expenses-list tbody tr")).to_have_count(4)
            page.locator("#question").fill("Combien ai-je dépensé en alimentation ?")
            page.get_by_role("button", name="Envoyer la question").click()
            expect(page.locator("#answer")).to_contain_text("72,50 €")
            expect(page.locator("#verdict")).to_have_text("Concordance confirmée par le backend.")
            for name in ("python", "sql"):
                expect(page.locator(f"#{name}-result")).to_contain_text("72,50")
                expect(page.locator(f"#{name}-result tbody tr")).to_have_count(3)
            expect(page.locator("#total-duration")).not_to_contain_text("Non disponible")
            expect(page.locator("#tool-trace")).to_be_hidden()
            claude["parsed"].update(status="needs_clarification", operation=None, category=None, message="Veuillez préciser la période.")
            page.locator("#question").fill("Combien ai-je dépensé récemment ?")
            page.get_by_role("button", name="Envoyer la question").click()
            expect(page.locator("#chat-status")).to_have_text("Veuillez préciser la période.")
            expect(page.locator("#results")).to_be_hidden()
            monkeypatch.delenv("ANTHROPIC_API_KEY")
            page.get_by_role("button", name="Envoyer la question").click()
            expect(page.locator("#chat-status")).to_contain_text("ANTHROPIC_API_KEY")
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
            section = page.locator("#tool-trace")
            expect(section).to_be_hidden()
            page.locator("#question").fill("Combien ai-je dépensé en alimentation ?")
            page.get_by_role("button", name="Envoyer la question").click()
            expect(section).to_be_visible()
            for text in ("Trace de l'agent", "verify_expenses", "total_by_category", "Alimentation",
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
            page.get_by_role("button", name="Envoyer la question").click()
            expect(section).to_be_hidden()
            expect(section.locator("article")).to_have_count(0)
            assert errors == []
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
