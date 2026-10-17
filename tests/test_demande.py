import json

import anthropic
import httpx2
import pytest

from miette import demande

NAMES = ["Sacha", "Noa"]


def _client(answer):
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "m",
            "content": [{"type": "text", "text": answer}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    client = anthropic.Anthropic(api_key="k", max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    return client, calls


def _understand(answer, text="une demande"):
    client, calls = _client(json.dumps(answer))
    return demande.understand(text, NAMES, key="k", model="m", client=client), calls


def test_a_story_keeps_its_theme_and_the_known_names_only():
    result, calls = _understand({"genre": "histoire", "sujet": "", "theme": "la tétine",
                                 "enfants": ["Noa", "Inconnue", "Noa"]})
    assert result == demande.Demande(kind="histoire", subject="", theme="la tétine", children=["Noa"])
    assert "Sacha, Noa" in calls[0]["messages"][0]["content"]


def test_a_coloring_keeps_its_subject():
    result, _ = _understand({"genre": "coloriage", "sujet": "la poule", "theme": "", "enfants": []})
    assert result.kind == "coloriage" and result.subject == "la poule"


@pytest.mark.parametrize("answer", [
    {"genre": "inconnu", "sujet": "", "theme": "", "enfants": []},
    {"genre": "coloriage", "sujet": " ", "theme": "", "enfants": []},
])
def test_what_miette_cannot_do_is_refused(answer):
    with pytest.raises(demande.DemandeError, match="reformuler"):
        _understand(answer)


def test_an_unreadable_answer_is_refused():
    client, _ = _client("pas du JSON")
    with pytest.raises(demande.DemandeError, match="reformuler"):
        demande.understand("une poule", NAMES, key="k", model="m", client=client)


def test_request_asks_for_structured_output_at_low_effort():
    request = demande.build_request("une poule", NAMES, "m")
    assert request["output_config"]["effort"] == "low"
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": demande.SCHEMA}
    assert request["fallbacks"] == "default"
