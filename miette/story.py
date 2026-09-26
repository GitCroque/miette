"""Écriture d'une histoire courte par un modèle de langage, via OpenRouter.

Public : des tout-petits de 2 ans, à qui un adulte lit des histoires du
quotidien dans le genre des T'choupi. La consigne suit l'âge calculé depuis
le mois de naissance de la fiche, pour grandir avec l'enfant.

Le modèle rend un texte brut dans un format fixe (titre, ligne vide, corps)
plutôt que du JSON : un guillemet mal échappé ne doit pas faire échouer
l'impression.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import date

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

SITUATIONS = (
    "l'heure du bain", "le repas", "l'heure de la sieste", "le coucher", "la crèche",
    "le parc", "s'habiller pour sortir", "les courses", "le jardin", "une promenade sous la pluie",
    "ranger les jouets", "le goûter", "se brosser les dents", "une journée à la maison",
)
EMOTIONS = (
    "une petite colère qui passe", "prêter un jouet", "la peur du noir", "un petit bobo",
    "attendre son tour", "dire au revoir le matin", "une grande fierté", "être un peu timide",
    "ne pas avoir envie de dormir",
)
OTHER_HEROES = ("un petit lapin", "un chaton", "un ourson", "un caneton", "une petite souris")

OCCASIONS = {
    "anniversaire": "Anniversaire",
    "fetes": "Fêtes",
    "voyage": "Voyage et visites",
    "premieres-fois": "Premières fois",
}
TRIPS = ("partir en vacances", "aller chez les grands-parents", "un copain vient jouer à la maison",
         "un voyage en train", "dormir ailleurs qu'à la maison")
FIRSTS = ("le premier jour à la crèche", "la visite chez le docteur", "la première fois chez le coiffeur",
          "la première fois à la piscine", "dire au revoir à la tétine", "la première nuit dans un grand lit")


def seasonal_party(day: date) -> str:
    return {
        1: "la galette des rois", 2: "le carnaval et les déguisements",
        3: "Pâques et la chasse aux œufs", 4: "Pâques et la chasse aux œufs",
        5: "une fête au jardin avec des fleurs", 6: "la fête de la musique",
        7: "une fête d'été au jardin", 8: "une fête d'été au jardin",
        9: "une fête avec des ballons", 10: "Halloween tout en douceur, avec des citrouilles et des déguisements rigolos",
        11: "Noël qui approche", 12: "Noël, le sapin et les lumières",
    }[day.month]


@dataclass(frozen=True)
class Band:
    label: str
    min_words: int
    max_words: int
    style: str


BANDS = (
    (36, Band("2 ans", 100, 150,
              "des phrases très courtes, de 5 à 10 mots, un vocabulaire du quotidien qu'un tout-petit "
              "connaît, des répétitions et des bruitages bienvenus")),
    (48, Band("3 ans", 120, 170,
              "des phrases courtes, un vocabulaire concret, quelques répétitions")),
    (10_000, Band("4 ans et plus", 140, 200,
                  "des phrases courtes et variées, un vocabulaire concret, une petite aventure")),
)


def age_in_months(birth: str, today: date) -> int | None:
    """Âge en mois depuis un mois de naissance « AAAA-MM »."""
    if not birth:
        return None
    year, month = (int(part) for part in birth.split("-")[:2])
    return (today.year - year) * 12 + today.month - month


def band_for(months: int | None) -> Band:
    if months is None:
        return BANDS[0][1]
    return next(band for limit, band in BANDS if months < limit)


def system_prompt(band: Band) -> str:
    return f"""Tu écris des petites histoires du quotidien pour des tout-petits de {band.label}, dans l'esprit des livres de T'choupi. Un adulte les lit à voix haute, l'enfant écoute puis garde le ticket imprimé.

Règles :
- entre {band.min_words} et {band.max_words} mots ;
- {band.style} ;
- une situation du quotidien, et au plus une petite émotion que l'histoire apprivoise avec douceur ;
- rien d'effrayant, une fin rassurante ;
- les adultes restent à peine évoqués : si l'un d'eux doit parler ou agir, écris « les parents », avec le verbe au pluriel (ou, à la crèche, la nounou si on te donne son nom), sans choisir entre maman et papa, jamais « un grand » ;
- aucun personnage existant de livre, de dessin animé ou de marque, aucun écran ;
- en français correct, avec la typographie française (guillemets « », espace avant ! ? : ;), sans emoji, sans tiret long.

Réponds uniquement dans ce format, sans rien avant ni après :
- première ligne : le titre, court, sans guillemets ;
- une ligne vide ;
- l'histoire, en trois à cinq paragraphes séparés par une ligne vide."""


def _join(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " et " + names[-1]


def _details(child: dict) -> list[str]:
    labels = (("doudou", "son doudou"), ("animaux", "les animaux de la maison"),
              ("creche", "sa crèche"), ("nounou", "sa nounou"), ("copains", "ses copains"))
    return [f"{label} : {child[key].strip()}" for key, label in labels if child.get(key, "").strip()]


def age_label(child: dict, today: date) -> str:
    months = age_in_months(child.get("naissance", ""), today)
    if months is None:
        return ""
    if months < 24:
        return f"{months} mois"
    return f"{months // 12} ans" + (" et demi" if months % 12 >= 6 else "")


def _next_birthday_age(child: dict, today: date) -> int | None:
    months = age_in_months(child.get("naissance", ""), today)
    if months is None:
        return None
    return months // 12 if months % 12 == 0 else months // 12 + 1


def brief(children: list[dict], occasion: str | None, recent_titles: list[str],
          today: date, rng: random.Random | None = None) -> tuple[Band, str]:
    """Choisit la tranche d'âge et compose la demande faite au modèle."""
    rng = rng or random.Random()
    months = [m for m in (age_in_months(c.get("naissance", ""), today) for c in children) if m is not None]
    band = band_for(min(months) if months else None)
    names = [c["prenom"] for c in children]
    lines = []

    # Qui est le héros : les enfants choisies ensemble, l'enfant seule, ou un
    # autre personnage de temps en temps (décision du 2026-09-26 : « ça varie »).
    if len(children) > 1:
        # Sans l'accord explicite, le modèle écrit « ils » pour deux petites filles.
        girls = sum(c.get("accord", "elle") == "elle" for c in children)
        if girls == len(children):
            group, pronoun = "des petites filles", "elles"
        elif girls == 0:
            group, pronoun = "des petits garçons", "ils"
        else:
            group, pronoun = "des enfants", "ils"
        lines.append(f"Les héros sont {_join(names)}, {group} qui passent un moment ensemble. "
                     f"Accorde au pluriel avec « {pronoun} ».")
    else:
        child = children[0]
        girl = child.get("accord", "elle") == "elle"
        age = age_label(child, today)
        who = f"{child['prenom']}, {'une petite fille' if girl else 'un petit garçon'}"
        who += f" de {age}" if age else ""
        if occasion is None and rng.random() < 0.35:
            candidates = [child[k] for k in ("doudou", "animaux") if child.get(k, "").strip()]
            other = rng.choice(candidates + list(OTHER_HEROES))
            lines.append(f"Cette fois, le héros est un autre personnage : {other}. "
                         f"L'histoire est lue à {who}, qui peut y apparaître.")
        else:
            lines.append(f"L'héroïne est {who}." if girl else f"Le héros est {who}.")

    if occasion == "anniversaire":
        ages = [a for a in (_next_birthday_age(c, today) for c in children) if a]
        suffix = f" ({ages[0]} ans)" if len(set(ages)) == 1 and ages else ""
        lines.append(f"Occasion : l'anniversaire de {_join(names)}{suffix}.")
    elif occasion == "fetes":
        lines.append(f"Occasion : {seasonal_party(today)}.")
    elif occasion == "voyage":
        lines.append(f"Occasion : {rng.choice(TRIPS)}.")
    elif occasion == "premieres-fois":
        lines.append(f"Occasion : {rng.choice(FIRSTS)}.")
    else:
        lines.append(f"Situation : {rng.choice(SITUATIONS)}.")
        if rng.random() < 0.6:
            lines.append(f"Petite émotion : {rng.choice(EMOTIONS)}.")

    details = [d for c in children for d in _details(c)]
    if details:
        lines.append("Détails de leur vraie vie, à glisser seulement s'ils servent l'histoire, "
                     "un ou deux au plus :\n- " + "\n- ".join(details))
    if recent_titles:
        lines.append("Histoires déjà racontées, à ne pas refaire : " + " ; ".join(recent_titles) + ".")
    return band, "\n".join(lines)


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


def build_request(system: str, user: str, model: str) -> dict:
    return {
        "model": model,
        "max_tokens": 900,
        "temperature": 1.0,
        # La réflexion du modèle n'apporte rien sur 150 mots et coûte des jetons.
        "reasoning": {"enabled": False},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
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
        raise StoryError("Crédit OpenRouter épuisé ou plafond mensuel atteint.")
    if response.status_code >= 400:
        raise StoryError(f"OpenRouter a répondu {response.status_code}.")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise StoryError("Réponse d'OpenRouter illisible.") from exc
    # Vu une fois le 2026-09-26 : un 200 avec un contenu nul, cause inconnue.
    return content or ""


def write(system: str, user: str, band: Band, *, key: str, model: str,
          client: httpx.Client | None = None) -> Story:
    """Demande une histoire, et la redemande une fois si elle est vide ou hors longueur."""
    if not key:
        raise StoryError("Aucune clé OpenRouter : renseigner OPENROUTER_API_KEY.")
    payload = build_request(system, user, model)
    low, high = round(band.min_words * 0.7), round(band.max_words * 1.3)
    owned = client is None
    client = client or httpx.Client(timeout=60)
    try:
        story = None
        for _ in range(2):
            raw = _complete(payload, key, client)
            if not raw.strip():
                continue
            story = parse(raw)
            if low <= story.words <= high:
                return story
        if story is None:
            raise StoryError("Le modèle a rendu deux réponses vides, réessayer dans un instant.")
        return story
    finally:
        if owned:
            client.close()
