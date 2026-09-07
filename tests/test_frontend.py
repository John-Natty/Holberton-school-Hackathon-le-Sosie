"""Validate that the frontend shell and the backend API are served together."""
import unittest

from app.wsgi import app


class FrontendSmokeTest(unittest.TestCase):
    def test_page_and_assets(self):
        with app.test_client() as client:
            page = client.get("/")
            self.assertEqual(page.status_code, 200)
            self.assertIn(b'lang="fr"', page.data)
            for asset in ("/static/css/style.css", "/static/js/app.js"):
                response = client.get(asset)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_business_routes_are_wired_up(self):
        with app.test_client() as client:
            self.assertEqual(client.get("/health").status_code, 200)
            self.assertEqual(client.get("/expenses").status_code, 200)
            self.assertEqual(client.get("/calculations/12").status_code, 404)
