import base64
import io
import urllib.error

import pytest
from PIL import Image, ImageDraw

from miette import drawing, images


def _png(mode="RGB", background="white", circle=True, size=1024):
    image = Image.new(mode, (size, size), background)
    if circle:
        ImageDraw.Draw(image).ellipse((200, 300, 824, 724), outline="black", width=24)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _answer(raw):
    return {"data": [{"b64_json": base64.b64encode(raw).decode(), "media_type": "image/png"}],
            "usage": {"cost": 0.04}}


def test_prompt_names_the_subject_without_its_article():
    prompt = images.coloring_prompt("l'éléphant")
    assert "éléphant" in prompt and "l'éléphant" not in prompt


def test_line_art_is_one_bit_at_ticket_width_and_trimmed():
    picture = images.line_art(_png(), 484)
    assert picture.mode == "1" and picture.width == 484
    # L'ovale occupe un peu plus de 40 % de la hauteur : le blanc autour est rogné.
    assert picture.height < 260
    assert drawing.MIN_INK < drawing.ink(picture) < drawing.MAX_INK


def test_transparent_background_becomes_white():
    picture = images.line_art(_png(mode="RGBA", background=(0, 0, 0, 0)), 484)
    assert drawing.ink(picture) < drawing.MAX_INK


@pytest.mark.parametrize("raw, message", [
    (_png(background="black", circle=False), "trop noir"),
    (_png(circle=False), "vide"),
    (b"pas une image", "illisible"),
])
def test_unusable_images_are_refused(raw, message):
    with pytest.raises(images.UnusableImage, match=message):
        images.line_art(raw, 484)


def test_fetch_sends_the_model_and_returns_the_image(monkeypatch):
    sent = []
    monkeypatch.setattr(images, "_post", lambda body, key: sent.append((body, key)) or _answer(b"octets"))
    assert images.fetch("Coloriage", key="cle", model="microsoft/mai-image-2.6") == b"octets"
    body, key = sent[0]
    assert key == "cle" and body["model"] == "microsoft/mai-image-2.6" and body["prompt"] == "Coloriage"


def test_fetch_without_a_key_says_which_variable_to_set():
    with pytest.raises(images.ImageError, match="OPENROUTER_API_KEY"):
        images.fetch("Coloriage", key="", model="m")


@pytest.mark.parametrize("code, message", [(401, "refusée"), (402, "épuisé"), (404, "indisponible"), (500, "500")])
def test_http_errors_are_explained(monkeypatch, code, message):
    def refuse(body, key):
        raise urllib.error.HTTPError(images.URL, code, "erreur", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(images, "_post", refuse)
    with pytest.raises(images.ImageError, match=message):
        images.fetch("Coloriage", key="cle", model="m")


def test_draw_asks_again_when_the_image_is_unusable(monkeypatch):
    answers = iter([_answer(_png(circle=False)), _answer(_png())])
    calls = []
    monkeypatch.setattr(images, "_post", lambda body, key: calls.append(1) or next(answers))
    picture = images.draw("Coloriage", key="cle", model="m", width=484)
    assert picture.width == 484 and len(calls) == 2


def test_draw_does_not_retry_an_outage(monkeypatch):
    calls = []

    def unreachable(body, key):
        calls.append(1)
        raise urllib.error.URLError("pas de réseau")

    monkeypatch.setattr(images, "_post", unreachable)
    with pytest.raises(images.ImageError, match="injoignable"):
        images.draw("Coloriage", key="cle", model="m", width=484)
    assert len(calls) == 1


def test_a_moderation_refusal_is_named(monkeypatch):
    def refuse(body, key):
        raise urllib.error.HTTPError(images.URL, 400, "Bad Request", {}, io.BytesIO(
            b'{"error":{"message":"Azure MAI blocked this request through content moderation.","code":400}}'))

    monkeypatch.setattr(images, "_post", refuse)
    with pytest.raises(images.ImageError, match="modération"):
        images.fetch("Illustration", key="cle", model="m")
