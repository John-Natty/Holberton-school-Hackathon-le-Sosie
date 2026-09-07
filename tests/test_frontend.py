"""Validate the launch shell without supplying any business API."""
import unittest
from app import app


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

    def test_business_routes_are_not_simulated(self):
        with app.test_client() as client:
            for path in ("/expenses", "/health", "/calculations/12"):
                self.assertEqual(client.get(path).status_code, 404)
            for path in ("/imports", "/chat"):
                self.assertEqual(client.post(path).status_code, 404)
