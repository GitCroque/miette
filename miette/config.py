"""Réglages de Miette, lus dans l'environnement du conteneur."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    printer_host: str
    printer_port: int
    openrouter_key: str
    model: str
    data_dir: Path
    daily_limit: int


def load() -> Settings:
    return Settings(
        printer_host=os.environ.get("MIETTE_IMPRIMANTE", ""),
        printer_port=int(os.environ.get("MIETTE_IMPRIMANTE_PORT", "9100")),
        openrouter_key=os.environ.get("OPENROUTER_API_KEY", "").strip(),
        model=os.environ.get("MIETTE_MODELE", "anthropic/claude-sonnet-5"),
        data_dir=Path(os.environ.get("MIETTE_DONNEES", "data")),
        daily_limit=int(os.environ.get("MIETTE_LIMITE_JOUR", "20")),
    )
