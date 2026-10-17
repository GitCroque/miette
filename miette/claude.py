"""Appel à Claude par l'API Anthropic, commun aux histoires et aux dessins."""

from __future__ import annotations

import anthropic


class ClaudeError(Exception):
    """Échec compréhensible par un humain, affiché tel quel sur le téléphone."""


def client(key: str) -> anthropic.Anthropic:
    if not key:
        raise ClaudeError("Aucune clé Anthropic : renseigner ANTHROPIC_API_KEY.")
    return anthropic.Anthropic(api_key=key, timeout=90, max_retries=1)


def complete(payload: dict, client: anthropic.Anthropic) -> str:
    """Envoie la requête et rend le texte de la réponse, vide si le modèle n'a rien écrit."""
    try:
        message = client.beta.messages.create(**payload)
    except anthropic.AuthenticationError as exc:
        raise ClaudeError("Clé Anthropic refusée (ANTHROPIC_API_KEY) : à renouveler.") from exc
    except anthropic.RateLimitError as exc:
        raise ClaudeError("Anthropic demande de patienter, réessayer dans un instant.") from exc
    except anthropic.APIStatusError as exc:
        if exc.status_code == 402:
            raise ClaudeError("Crédit Anthropic épuisé ou plafond de dépense atteint.") from exc
        raise ClaudeError(f"Anthropic a répondu {exc.status_code}.") from exc
    except anthropic.APIConnectionError as exc:
        raise ClaudeError(f"Anthropic injoignable : {type(exc).__name__}.") from exc

    if message.stop_reason == "refusal":
        raise ClaudeError("Le modèle a refusé cette demande, réessayer.")
    return "".join(block.text for block in message.content if block.type == "text")
