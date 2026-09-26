import importlib

import pytest
from fastapi.testclient import TestClient

from miette import printer, story


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MIETTE_DONNEES", str(tmp_path))
    monkeypatch.setenv("MIETTE_IMPRIMANTE", "imprimante.test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "cle-de-test")
    monkeypatch.setenv("MIETTE_LIMITE_JOUR", "2")
    import miette.app as app_module
    app_module = importlib.reload(app_module)

    printed = []
    monkeypatch.setattr(printer, "status", lambda host, port: printer.Status(True, "Prête."))
    monkeypatch.setattr(printer, "print_image", lambda host, port, image: printed.append(image))
    monkeypatch.setattr(story, "write", lambda theme, name, pronoun, key, model: story.Story(
        f"Histoire de {theme}", ("Un paragraphe.", "Un autre.")))
    test_client = TestClient(app_module.app)
    test_client.printed = printed
    return test_client


def test_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Miette" in response.text


def test_story_is_printed_and_logged(client):
    response = client.post("/api/histoire", json={"theme": "la mer", "prenom": "Lou", "pronom": "il"})
    assert response.status_code == 200
    data = response.json()
    assert data["titre"] == "Histoire de la mer"
    assert len(client.printed) == 1 and client.printed[0].width == 512

    state = client.get("/api/etat").json()
    assert state["histoires"][0]["id"] == data["id"]
    assert state["restantes"] == 1


def test_reprint_does_not_count(client):
    story_id = client.post("/api/histoire", json={"theme": "la mer"}).json()["id"]
    assert client.post(f"/api/reimprimer/{story_id}").status_code == 200
    assert len(client.printed) == 2
    assert client.get("/api/etat").json()["restantes"] == 1


def test_daily_limit(client):
    for _ in range(2):
        assert client.post("/api/histoire", json={"theme": "la mer"}).status_code == 200
    response = client.post("/api/histoire", json={"theme": "la mer"})
    assert response.status_code == 429


def test_printer_problem_stops_before_writing(client, monkeypatch):
    monkeypatch.setattr(printer, "status", lambda host, port: printer.Status(False, "Plus de papier."))
    monkeypatch.setattr(story, "write", lambda *a, **k: pytest.fail("histoire payée pour rien"))
    response = client.post("/api/histoire", json={"theme": "la mer"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Plus de papier."


def test_unknown_pronoun_is_rejected(client):
    assert client.post("/api/histoire", json={"pronom": "iel"}).status_code == 422
