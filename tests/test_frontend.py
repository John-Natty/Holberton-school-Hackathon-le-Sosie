"""The frontend and API use one Flask application and an isolated database."""


def test_page_and_assets(client):
    page = client.get("/")
    assert page.status_code == 200
    assert b'lang="fr"' in page.data
    for asset in ("/static/css/style.css", "/static/js/app.js"):
        response = client.get(asset)
        assert response.status_code == 200
        response.close()


def test_business_routes_are_wired_up(client):
    assert client.get("/health").get_json() == {"status": "ok"}
    assert client.get("/expenses").get_json() == []
    assert client.get("/calculations/12").status_code == 404
