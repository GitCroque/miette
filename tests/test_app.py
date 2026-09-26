import importlib

import pytest
from fastapi.testclient import TestClient

from miette import printer, story

LOU = {"prenom": "Lou", "naissance": "2024-10", "accord": "elle", "doudou": "Lapinou"}
MAX = {"prenom": "Max", "naissance": "2024-12", "accord": "il"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MIETTE_DONNEES", str(tmp_path))
    monkeypatch.setenv("MIETTE_IMPRIMANTE", "imprimante.test")
    monkeypatch.setenv("OPENROUTER_API_KEY", "cle-de-test")
    monkeypatch.setenv("MIETTE_LIMITE_JOUR", "3")
    import miette.app as app_module
    app_module = importlib.reload(app_module)

    printed, briefs = [], []
    monkeypatch.setattr(printer, "status", lambda host, port: printer.Status(True, "Prête."))
    monkeypatch.setattr(printer, "print_image", lambda host, port, image: printed.append(image))

    def fake_write(system, user, band, key, model):
        briefs.append(user)
        return story.Story(f"Histoire {len(briefs)}", ("Un paragraphe.", "Un autre."))

    monkeypatch.setattr(story, "write", fake_write)
    test_client = TestClient(app_module.app)
    test_client.printed, test_client.briefs = printed, briefs
    return test_client


def _children(client, *profiles):
    response = client.put("/api/enfants", json=list(profiles))
    assert response.status_code == 200
    return [c["id"] for c in response.json()]


def test_page_is_served(client):
    assert "Miette" in client.get("/").text


def test_profiles_get_ids_and_persist(client):
    ids = _children(client, LOU, MAX)
    assert len(set(ids)) == 2
    assert [c["prenom"] for c in client.get("/api/enfants").json()] == ["Lou", "Max"]
    assert [c["prenom"] for c in client.get("/api/etat").json()["enfants"]] == ["Lou", "Max"]


def test_invalid_birth_month_is_rejected(client):
    assert client.put("/api/enfants", json=[{**LOU, "naissance": "2024-13"}]).status_code == 422


def test_preview_does_not_print(client):
    lou, _ = _children(client, LOU, MAX)
    data = client.post("/api/histoires", json={"enfants": [lou]}).json()
    assert data["pour"] == "Lou" and data["imprimee"] is None
    assert client.printed == []
    assert "Lapinou" in client.briefs[0]


def test_print_then_reprint(client):
    lou, max_ = _children(client, LOU, MAX)
    story_id = client.post("/api/histoires", json={"enfants": [lou, max_], "occasion": "fetes"}).json()["id"]
    first = client.post(f"/api/histoires/{story_id}/imprimer").json()
    assert first["imprimee"] and first["pour"] == "Lou et Max"
    assert client.post(f"/api/histoires/{story_id}/imprimer").status_code == 200
    assert len(client.printed) == 2 and client.printed[0].width == 512
    state = client.get("/api/etat").json()
    assert [h["id"] for h in state["histoires"]] == [story_id]
    assert state["restantes"] == 2


def test_another_story_avoids_recent_titles(client):
    lou, _ = _children(client, LOU, MAX)
    client.post("/api/histoires", json={"enfants": [lou]})
    client.post("/api/histoires", json={"enfants": [lou]})
    assert "Histoire 1" in client.briefs[1]


def test_daily_limit_counts_previews(client):
    lou, _ = _children(client, LOU, MAX)
    for _ in range(3):
        assert client.post("/api/histoires", json={"enfants": [lou]}).status_code == 200
    assert client.post("/api/histoires", json={"enfants": [lou]}).status_code == 429


def test_unknown_child_is_rejected(client):
    _children(client, LOU)
    assert client.post("/api/histoires", json={"enfants": ["inconnu"]}).status_code == 422


def test_unknown_occasion_is_rejected(client):
    lou, = _children(client, LOU)
    assert client.post("/api/histoires", json={"enfants": [lou], "occasion": "mariage"}).status_code == 422


def test_printer_problem_is_reported(client, monkeypatch):
    lou, = _children(client, LOU)
    story_id = client.post("/api/histoires", json={"enfants": [lou]}).json()["id"]
    monkeypatch.setattr(printer, "status", lambda host, port: printer.Status(False, "Plus de papier."))
    response = client.post(f"/api/histoires/{story_id}/imprimer")
    assert response.status_code == 503 and response.json()["detail"] == "Plus de papier."
    assert client.get("/api/etat").json()["histoires"] == []


def test_printer_state_is_cached_between_pages(client, monkeypatch):
    calls = []
    monkeypatch.setattr(printer, "status", lambda host, port: calls.append(1) or printer.Status(True, "Prête."))
    for _ in range(3):
        client.get("/api/etat")
    assert len(calls) == 1


def test_printing_always_checks_the_printer_again(client, monkeypatch):
    lou, = _children(client, LOU)
    client.get("/api/etat")
    story_id = client.post("/api/histoires", json={"enfants": [lou]}).json()["id"]
    monkeypatch.setattr(printer, "status", lambda host, port: printer.Status(False, "Le capot est ouvert."))
    assert client.post(f"/api/histoires/{story_id}/imprimer").json()["detail"] == "Le capot est ouvert."
