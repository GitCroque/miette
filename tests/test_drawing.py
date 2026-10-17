import anthropic
import httpx2
import pytest

from miette import drawing

CIRCLE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
          '<circle cx="256" cy="256" r="180" fill="none" stroke="#000" stroke-width="12"/></svg>')
BLACK = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
         '<rect width="512" height="512" fill="#000"/></svg>')


def _client(texts):
    answers = iter(texts)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "m",
            "content": [{"type": "text", "text": next(answers)}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
        })

    client = anthropic.Anthropic(api_key="k", max_retries=0,
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    return client, calls


def test_sanitize_keeps_shapes_and_drops_the_rest():
    raw = ('Voici le dessin :\n<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" onload="x()">'
           '<script>alert(1)</script><image href="file:///etc/passwd"/><text>Chat</text>'
           '<use href="#a"/><use href="http://exemple.fr/a.svg#b"/><circle id="a" r="5"/></svg> Bonne journée')
    svg = drawing.sanitize(raw)
    assert "<circle" in svg and 'href="#a"' in svg
    for gone in ("script", "<image", "<text", "onload", "exemple.fr", "Bonne journée"):
        assert gone not in svg


@pytest.mark.parametrize("raw", [
    "Je ne peux pas dessiner ça.",
    '<svg viewBox="0 0 10 10"><circle r="2"/>',
    '<!DOCTYPE svg [<!ENTITY a "b">]><svg viewBox="0 0 10 10">&a;</svg>',
    '<svg xmlns="http://www.w3.org/2000/svg"><circle r="2"/></svg>',
])
def test_sanitize_rejects_what_is_not_a_drawing(raw):
    with pytest.raises(drawing.DrawingError):
        drawing.sanitize(raw)


def test_render_is_one_bit_at_the_requested_width():
    image = drawing.render(CIRCLE, 484)
    assert image.mode == "1" and image.size == (484, 484)
    assert drawing.MIN_INK < drawing.ink(image) < drawing.MAX_INK


def test_draw_asks_again_when_the_answer_is_not_a_drawing():
    client, calls = _client(["Désolé, je n'ai pas compris.", CIRCLE])
    svg = drawing.draw("Coloriage : chat.", key="k", model="m", client=client)
    assert "<circle" in svg and len(calls) == 2
    assert calls[0].headers["x-api-key"] == "k"


def test_draw_refuses_a_drawing_filled_with_black():
    client, calls = _client([BLACK, BLACK])
    with pytest.raises(drawing.DrawingError, match="trop noir"):
        drawing.draw("Coloriage : chat.", key="k", model="m", client=client)
    assert len(calls) == 2


def test_request_uses_medium_effort_and_falls_back_on_refusal():
    request = drawing.build_request("Coloriage : chat.", "m")
    assert request["output_config"] == {"effort": "medium"}
    assert request["fallbacks"] == "default" and request["system"] == drawing.SYSTEM
    assert "temperature" not in request and "thinking" not in request


def test_subjects_avoid_recent_ones():
    assert drawing.pick_subject(list(drawing.SUBJECTS[:-1])) == drawing.SUBJECTS[-1]
    assert drawing.pick_subject(list(drawing.SUBJECTS)) in drawing.SUBJECTS


def test_noun_drops_the_article():
    assert drawing.noun("l'éléphant") == "éléphant"
    assert drawing.noun("la vache") == "vache"
    assert "chat" in drawing.coloring_prompt("le chat")


def test_a_theme_keeps_to_its_subjects():
    label, vehicles = drawing.CATEGORIES["vehicules"]
    assert label == "Véhicules"
    assert drawing.pick_subject([], "vehicules") in vehicles
    assert drawing.pick_subject(list(vehicles[:-1]), "vehicules") == vehicles[-1]
    assert len(set(drawing.SUBJECTS)) == len(drawing.SUBJECTS)
