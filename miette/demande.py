"""Demande libre du parent, rangée par Claude : une histoire sur un thème, ou un coloriage.

Le champ libre, écarté au cadrage du 2026-09-26, a été demandé par Julien le
2026-10-17 (« un coloriage d'une poule », « une histoire sur le thème de la
tétine »). Un premier appel court, en sortie structurée, range la demande ; la
suite passe par les chemins habituels, avec aperçu avant d'imprimer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from . import claude

MAX_SUBJECT = 60
MAX_THEME = 120

SYSTEM = """Tu ranges la demande d'un parent pour Miette, qui imprime des histoires et des coloriages pour des enfants de 2 ans.
- « histoire » : le parent veut une histoire. theme : le thème ou la situation demandée, en quelques mots (« la tétine », « le premier jour à la piscine »), vide s'il n'en donne pas. sujet : vide.
- « coloriage » : le parent veut un coloriage, un dessin ou une image. sujet : ce qu'il faut dessiner, précédé de son article (« la poule », « le camion de pompiers »). theme : vide.
- « inconnu » : ni l'un ni l'autre, ou une demande qui ne convient pas à un tout-petit.
enfants : les prénoms cités dans la demande, seulement parmi ceux de la liste fournie et écrits comme dans la liste ; vide si aucun."""

SCHEMA = {
    "type": "object",
    "properties": {
        "genre": {"type": "string", "enum": ["histoire", "coloriage", "inconnu"]},
        "sujet": {"type": "string"},
        "theme": {"type": "string"},
        "enfants": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["genre", "sujet", "theme", "enfants"],
    "additionalProperties": False,
}


class DemandeError(claude.ClaudeError):
    """Demande que Miette ne sait pas traiter : à reformuler par le parent."""


@dataclass(frozen=True)
class Demande:
    kind: str
    subject: str
    theme: str
    children: list[str]


def build_request(text: str, names: list[str], model: str) -> dict:
    known = ", ".join(names) if names else "aucun"
    return {
        "model": model,
        "max_tokens": 2000,
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        "system": SYSTEM,
        "messages": [{"role": "user", "content": f"Enfants connus : {known}.\nDemande du parent : {text}"}],
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }


def understand(text: str, names: list[str], *, key: str, model: str,
               client: anthropic.Anthropic | None = None) -> Demande:
    owned = client is None
    client = client or claude.client(key)
    try:
        raw = claude.complete(build_request(text, names, model), client)
    finally:
        if owned:
            client.close()
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise DemandeError("Miette n'a pas compris la demande : la reformuler.") from exc

    kind = data.get("genre")
    subject = str(data.get("sujet", "")).strip()[:MAX_SUBJECT]
    theme = str(data.get("theme", "")).strip()[:MAX_THEME]
    if kind not in ("histoire", "coloriage") or (kind == "coloriage" and not subject):
        raise DemandeError("Miette sait faire une histoire ou un coloriage : reformuler la demande.")
    children = [n for n in dict.fromkeys(data.get("enfants") or []) if n in names]
    return Demande(kind=kind, subject=subject, theme=theme, children=children)
