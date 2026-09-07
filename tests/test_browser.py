"""Real browser -> Flask -> installed Anthropic SDK -> both SQLite calculators.

Only Anthropic's external HTTP response is replaced by the claude test fixture.
"""
from threading import Thread

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from conftest import CSV_CONTENT


def test_browser_happy_path(application, claude, monkeypatch):
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
