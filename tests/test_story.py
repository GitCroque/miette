import httpx
import pytest

from miette import story


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
    assert parsed.title == "Le crabe"
    assert parsed.paragraphs == ("Il était une fois un crabe.", "Fin.")


def test_parse_rejects_title_only():
    with pytest.raises(story.StoryError):
        story.parse("Juste un titre")


def test_prompt_names_the_child_and_the_theme():
    payload = story.build_request("la mer", "  Lou  ", "il", "modele/test")
    assert payload["model"] == "modele/test"
    user = payload["messages"][1]["content"]
    assert "Thème : la mer." in user
    assert "un petit garçon qui s'appelle Lou" in user


def test_prompt_without_name():
    assert "Pas de prénom" in story.user_prompt("la mer", "", "elle")


def test_pick_theme_falls_back_to_surprise():
    assert story.pick_theme("   ") in story.SURPRISE_THEMES
    assert story.pick_theme("  les   pompiers ") == "les pompiers"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _answer(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_write_retries_once_when_too_short():
    calls = []
    long_body = " ".join(["mot"] * 100)

    def handler(request):
        calls.append(request)
        return _answer("Titre\n\nTrop court." if len(calls) == 1 else f"Titre\n\n{long_body}")

    written = story.write("la mer", "Lou", "elle", key="k", model="m", client=_client(handler))
    assert len(calls) == 2
    assert written.words == 100
    assert calls[0].headers["Authorization"] == "Bearer k"


def test_write_explains_a_refused_key():
    with pytest.raises(story.StoryError, match="OPENROUTER_API_KEY"):
        story.write("la mer", "", "elle", key="k", model="m",
                    client=_client(lambda r: httpx.Response(401)))


def test_write_without_key():
    with pytest.raises(story.StoryError, match="Aucune clé"):
        story.write("la mer", "", "elle", key="", model="m")
