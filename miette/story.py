"""Écriture d'une histoire courte par un modèle de langage, via OpenRouter.

Le modèle rend un texte brut dans un format fixe (titre, ligne vide, corps)
plutôt que du JSON : un guillemet mal échappé dans une histoire ne doit pas
faire échouer l'impression.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

MIN_WORDS, MAX_WORDS = 80, 150
# Au-delà de ces bornes, on redemande une fois. Entre les deux, on garde :
# quelques mots de trop ne valent pas un second appel.
RETRY_BELOW, RETRY_ABOVE = 60, 190

SURPRISE_THEMES = (
    "un escargot pressé",
    "la pluie",
    "un nuage qui veut jouer",
    "le potager",
    "un doudou perdu",
    "la neige",
    "un petit train",
    "les fourmis",
    "la lune",
    "un pique-nique",
    "le marché",
    "les bulles de savon",
)

SYSTEM_PROMPT = f"""Tu écris des histoires courtes pour un enfant de 3 à 5 ans. Un adulte les lit à voix haute, puis l'enfant garde le ticket imprimé.

Règles :
- entre {MIN_WORDS} et {MAX_WORDS} mots ;
- des phrases courtes, un vocabulaire concret que l'enfant connaît ;
- une seule petite péripétie, jamais effrayante, et une fin douce et rassurante ;
- si l'on te donne un prénom, cet enfant est le héros ou l'héroïne de l'histoire ;
- aucun personnage de dessin animé, de livre ou de marque, aucun écran, pas de morale appuyée ;
- en français correct, avec la typographie française (guillemets « », espace avant ! ? : ;), sans emoji, sans tiret long.

Réponds uniquement dans ce format, sans rien avant ni après :
- première ligne : le titre, court, sans guillemets ;
- une ligne vide ;
- l'histoire, en deux à quatre paragraphes séparés par une ligne vide."""


class StoryError(Exception):
    """Échec compréhensible par un humain, affiché tel quel sur le téléphone."""


@dataclass(frozen=True)
class Story:
    title: str
    paragraphs: tuple[str, ...]

    @property
    def words(self) -> int:
        return sum(len(p.split()) for p in self.paragraphs)

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)


def pick_theme(theme: str) -> str:
    theme = " ".join(theme.split())[:80]
    return theme or random.choice(SURPRISE_THEMES)


def user_prompt(theme: str, name: str, pronoun: str) -> str:
    name = " ".join(name.split())[:30]
    if name:
        child = "une petite fille" if pronoun == "elle" else "un petit garçon"
        hero = f"Le héros est {child} qui s'appelle {name}."
    else:
        hero = "Pas de prénom : invente un petit personnage attachant."
    return f"Thème : {theme}.\n{hero}"


def build_request(theme: str, name: str, pronoun: str, model: str) -> dict:
    return {
        "model": model,
        "max_tokens": 700,
        "temperature": 1.0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(theme, name, pronoun)},
        ],
    }


_TITLE_NOISE = re.compile(r"^(?:#+\s*|\*+|titre\s*:\s*)", re.IGNORECASE)


def parse(raw: str) -> Story:
    """Découpe la réponse du modèle en titre et paragraphes."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw.strip()) if b.strip()]
    if not blocks:
        raise StoryError("Le modèle a rendu une réponse vide.")

    head = blocks[0].splitlines()
    title = _TITLE_NOISE.sub("", head[0].strip()).strip("*").strip().strip("«»\"' ")
    # Titre collé au premier paragraphe, sans ligne vide entre les deux.
    rest = head[1:]
    paragraphs = [" ".join(rest)] if rest else []
    paragraphs += [" ".join(line.strip() for line in b.splitlines()) for b in blocks[1:]]
    paragraphs = [p for p in paragraphs if p]

    if not title or not paragraphs:
        raise StoryError("Le modèle n'a pas respecté le format titre puis histoire.")
    return Story(title=title, paragraphs=tuple(paragraphs))


def _complete(payload: dict, key: str, client: httpx.Client) -> str:
    try:
        response = client.post(
            OPENROUTER_URL,
            json=payload,
            headers={"Authorization": f"Bearer {key}", "X-Title": "Miette"},
        )
    except httpx.HTTPError as exc:
        raise StoryError(f"OpenRouter injoignable : {type(exc).__name__}.") from exc

    if response.status_code == 401:
        raise StoryError("Clé OpenRouter refusée (OPENROUTER_API_KEY) : à renouveler.")
    if response.status_code == 402:
        raise StoryError("Crédit OpenRouter épuisé.")
    if response.status_code >= 400:
        raise StoryError(f"OpenRouter a répondu {response.status_code}.")

    try:
        return response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise StoryError("Réponse d'OpenRouter illisible.") from exc


def write(theme: str, name: str, pronoun: str, *, key: str, model: str,
          client: httpx.Client | None = None) -> Story:
    """Demande une histoire, et la redemande une fois si sa longueur dérape."""
    if not key:
        raise StoryError("Aucune clé OpenRouter : renseigner OPENROUTER_API_KEY.")
    payload = build_request(theme, name, pronoun, model)
    owned = client is None
    client = client or httpx.Client(timeout=60)
    try:
        story = parse(_complete(payload, key, client))
        if not RETRY_BELOW <= story.words <= RETRY_ABOVE:
            story = parse(_complete(payload, key, client))
        return story
    finally:
        if owned:
            client.close()
