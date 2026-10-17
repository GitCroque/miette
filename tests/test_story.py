import random
from datetime import date

import anthropic
import httpx2
import pytest

from miette import story

TODAY = date(2026, 11, 15)
LOU = {"id": "a", "prenom": "Lou", "naissance": "2024-10", "accord": "elle",
       "doudou": "Lapinou", "animaux": "Pistache le chat", "creche": "", "nounou": "", "copains": "Léo"}
MAX = {"id": "b", "prenom": "Max", "naissance": "2024-12", "accord": "il"}


def test_parse_title_then_paragraphs():
    raw = "Le crabe qui dansait\n\nLéa marche sur la plage.\nElle voit un crabe.\n\nIls dansent ensemble."
    parsed = story.parse(raw)
    assert parsed.title == "Le crabe qui dansait"
    assert parsed.paragraphs == ("Léa marche sur la plage. Elle voit un crabe.", "Ils dansent ensemble.")
    assert parsed.words == 12


@pytest.mark.parametrize("head", ["# Le crabe", "**Le crabe**", "Titre : Le crabe", "« Le crabe »", '"Le crabe"'])
def test_parse_strips_title_decorations(head):
    assert story.parse(f"{head}\n\nUne histoire.").title == "Le crabe"


def test_parse_title_glued_to_first_paragraph():
    parsed = story.parse("Le crabe\nIl était une fois un crabe.\n\nFin.")
    assert parsed.paragraphs == ("Il était une fois un crabe.", "Fin.")


def test_parse_rejects_title_only():
    with pytest.raises(story.StoryError):
        story.parse("Juste un titre")


def test_age_in_months():
    assert story.age_in_months("2024-10", TODAY) == 25
    assert story.age_in_months("", TODAY) is None


@pytest.mark.parametrize("months,label", [(None, "2 ans"), (23, "2 ans"), (35, "2 ans"), (36, "3 ans"), (50, "4 ans et plus")])
def test_band_follows_age(months, label):
    assert story.band_for(months).label == label


def test_system_prompt_keeps_parents_out_and_sets_length():
    prompt = story.system_prompt(story.band_for(25))
    assert "entre 100 et 150 mots" in prompt
    assert "sans choisir entre maman et papa" in prompt and "« les parents »" in prompt
    assert "T'choupi" in prompt


def test_brief_for_one_child_uses_the_profile():
    band, user = story.brief([LOU], None, [], TODAY, random.Random(1))
    assert band.label == "2 ans"
    assert "Lou" in user and "2 ans" in user
    assert "Lapinou" in user and "Léo" in user
    assert "Situation :" in user


def test_brief_sometimes_picks_another_hero():
    heroes = set()
    for seed in range(40):
        _, user = story.brief([LOU], None, [], TODAY, random.Random(seed))
        heroes.add("autre personnage" in user)
    assert heroes == {True, False}


def test_brief_for_two_children_uses_the_youngest_band():
    old = {**MAX, "naissance": "2022-01"}
    band, user = story.brief([LOU, old], None, [], TODAY, random.Random(3))
    assert band.label == "2 ans"
    assert "Lou et Max" in user


def test_birthday_names_the_coming_age():
    _, user = story.brief([LOU], "anniversaire", [], TODAY, random.Random(0))
    assert "l'anniversaire de Lou (3 ans)" in user
    birthday_month = date(2026, 10, 3)
    _, user = story.brief([LOU], "anniversaire", [], birthday_month, random.Random(0))
    assert "(2 ans)" in user


def test_parties_follow_the_season():
    _, user = story.brief([LOU], "fetes", [], date(2026, 12, 1), random.Random(0))
    assert "Noël" in user


def test_recent_titles_are_excluded():
    _, user = story.brief([LOU], None, ["Le bain de Lou"], TODAY, random.Random(0))
    assert "Le bain de Lou" in user


def _client(handler):
    return anthropic.Anthropic(api_key="k", max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def _answer(text, stop_reason="end_turn"):
    content = [{"type": "text", "text": text}] if text else []
    return httpx2.Response(200, json={
        "id": "msg_test", "type": "message", "role": "assistant", "model": "m", "content": content,
        "stop_reason": stop_reason, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
    })


BAND = story.band_for(25)
BODY = " ".join(["mot"] * 120)


def test_write_retries_when_too_short():
    calls = []

    def handler(request):
        calls.append(request)
        return _answer("Titre\n\nTrop court." if len(calls) == 1 else f"Titre\n\n{BODY}")

    written = story.write("s", "u", BAND, key="k", model="m", client=_client(handler))
    assert len(calls) == 2 and written.words == 120
    assert calls[0].headers["x-api-key"] == "k"


def test_write_retries_after_an_empty_answer():
    answers = iter([_answer(""), _answer(f"Titre\n\n{BODY}")])
    written = story.write("s", "u", BAND, key="k", model="m", client=_client(lambda r: next(answers)))
    assert written.title == "Titre"


def test_write_gives_up_after_two_empty_answers():
    empty = _answer("")
    with pytest.raises(story.StoryError, match="vides"):
        story.write("s", "u", BAND, key="k", model="m", client=_client(lambda r: empty))


def test_write_explains_a_refused_key():
    refused = httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}})
    with pytest.raises(story.StoryError, match="ANTHROPIC_API_KEY"):
        story.write("s", "u", BAND, key="k", model="m", client=_client(lambda r: refused))


def test_write_explains_a_refusal():
    with pytest.raises(story.StoryError, match="refusé"):
        story.write("s", "u", BAND, key="k", model="m", client=_client(lambda r: _answer("", "refusal")))


def test_write_without_key():
    with pytest.raises(story.StoryError, match="Aucune clé"):
        story.write("s", "u", BAND, key="", model="m")


def test_request_keeps_thinking_short_and_falls_back_on_refusal():
    request = story.build_request("s", "u", "m")
    assert request["output_config"] == {"effort": "low"}
    assert request["fallbacks"] == "default"
    # Opus 5.5 refuse la température et la réflexion coupée.
    assert "temperature" not in request and "thinking" not in request


def test_two_girls_are_agreed_in_the_feminine():
    zoe = {**LOU, "id": "c", "prenom": "Zoé"}
    _, user = story.brief([LOU, zoe], None, [], TODAY, random.Random(0))
    assert "des petites filles" in user and "« elles »" in user


def test_mixed_children_are_agreed_in_the_masculine():
    _, user = story.brief([LOU, MAX], None, [], TODAY, random.Random(0))
    assert "« ils »" in user
