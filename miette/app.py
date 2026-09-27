"""Serveur web de Miette : une page pour le téléphone, une API pour imprimer.

Déroulé décidé le 2026-09-26 : choisir l'enfant (ou les deux), Surprise ou
une occasion, lire l'aperçu, puis imprimer ou en demander une autre.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, printer, story, ticket
from .store import Store, StoredStory

STATIC = Path(__file__).parent / "static"
FONTS = Path(__file__).parent / "fonts"
MAX_CHILDREN = 6

log = logging.getLogger("miette")
settings = config.load()
store = Store(settings.data_dir)
# Une seule impression à la fois : deux appuis rapprochés ne doivent pas
# entremêler deux tickets.
printing = threading.Lock()

# Chaque page ouverte demande l'état toutes les 30 secondes, et l'imprimante
# ne sert qu'une connexion à la fois : l'état affiché est gardé 5 secondes, et
# pendant une impression on rend le dernier connu sans ouvrir de connexion.
STATUS_MAX_AGE = 5.0
_status_lock = threading.Lock()
_status_cache: dict = {"at": 0.0, "value": None}


def printer_status(fresh: bool = False) -> printer.Status:
    with _status_lock:
        cached = _status_cache["value"]
        if not fresh:
            if cached is not None and time.monotonic() - _status_cache["at"] < STATUS_MAX_AGE:
                return cached
            if printing.locked():
                return cached or printer.Status(True, "Impression en cours.")
        value = printer.status(settings.printer_host, settings.printer_port)
        _status_cache.update(at=time.monotonic(), value=value)
        return value

app = FastAPI(title="Miette", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
# Les polices des tickets servent aussi à la page : rien n'est chargé ailleurs.
app.mount("/fonts", StaticFiles(directory=FONTS), name="fonts")


class Child(BaseModel):
    id: str = Field("", max_length=16)
    prenom: str = Field(min_length=1, max_length=30)
    naissance: str = Field("", pattern=r"^(\d{4}-(0[1-9]|1[0-2]))?$")
    accord: Literal["elle", "il"] = "elle"
    doudou: str = Field("", max_length=80)
    animaux: str = Field("", max_length=120)
    creche: str = Field("", max_length=80)
    nounou: str = Field("", max_length=80)
    copains: str = Field("", max_length=120)


class Favorite(BaseModel):
    favori: bool


class StoryRequest(BaseModel):
    enfants: list[str] = Field(min_length=1, max_length=MAX_CHILDREN)
    occasion: Literal["anniversaire", "fetes", "voyage", "premieres-fois"] | None = None


def _names(ids: list[str]) -> str:
    by_id = {c["id"]: c["prenom"] for c in store.children()}
    names = [by_id.get(i, "") for i in ids]
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " et " + names[-1]


def _public(entry: StoredStory) -> dict:
    return {
        "id": entry.id,
        "titre": entry.title,
        "texte": "\n\n".join(entry.paragraphs),
        "pour": _names(entry.children),
        "occasion": entry.occasion,
        "date": entry.created,
        "imprimee": entry.printed,
        "favori": entry.favorite,
    }


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    # Revalider à chaque ouverture : sans cela, un téléphone peut garder l'ancienne page
    # quelque temps après un déploiement (304 si rien n'a changé).
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> FileResponse:
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/apple-touch-icon.png", include_in_schema=False)
def touch_icon() -> FileResponse:
    return FileResponse(STATIC / "icon-180.png")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/etat")
def state() -> dict:
    """Tout ce que l'accueil affiche, en un seul appel."""
    status = printer_status()
    last = store.printed(1)
    return {
        "imprimante": status.message,
        "prete": status.ready,
        "papier_bas": status.paper_low,
        "cle": bool(settings.openrouter_key),
        "restantes": max(0, settings.daily_limit - store.written_today()),
        "enfants": [{"id": c["id"], "prenom": c["prenom"], "age": story.age_label(c, date.today())}
                    for c in store.children()],
        "occasions": story.OCCASIONS,
        "derniere": _public(last[0]) if last else None,
        "favoris": [_public(e) for e in store.printed(3, favorites_only=True)],
    }


@app.get("/api/enfants")
def children() -> list[dict]:
    return store.children()


@app.put("/api/enfants")
def save_children(children: list[Child]) -> list[dict]:
    if len(children) > MAX_CHILDREN:
        raise HTTPException(422, f"{MAX_CHILDREN} fiches au plus.")
    return store.save_children([c.model_dump() for c in children])


@app.get("/api/histoires")
def list_stories(favoris: bool = False) -> list[dict]:
    """L'historique : les histoires imprimées, jamais les aperçus écartés."""
    return [_public(e) for e in store.printed(500, favorites_only=favoris)]


@app.get("/api/histoires/{story_id}")
def read_story(story_id: str) -> dict:
    entry = store.story(story_id)
    if entry is None:
        raise HTTPException(404, "Histoire introuvable.")
    return _public(entry)


@app.post("/api/histoires/{story_id}/favori")
def set_favorite(story_id: str, body: Favorite) -> dict:
    if store.story(story_id) is None:
        raise HTTPException(404, "Histoire introuvable.")
    store.set_favorite(story_id, body.favori)
    return _public(store.story(story_id))


@app.delete("/api/histoires/{story_id}")
def delete_story(story_id: str) -> dict:
    if store.story(story_id) is None:
        raise HTTPException(404, "Histoire introuvable.")
    store.delete(story_id)
    return {"ok": True}


@app.post("/api/histoires")
def write_story(request: StoryRequest) -> dict:
    """Écrit une histoire et la renvoie en aperçu, sans l'imprimer."""
    by_id = {c["id"]: c for c in store.children()}
    chosen = [by_id[i] for i in dict.fromkeys(request.enfants) if i in by_id]
    if not chosen:
        raise HTTPException(422, "Aucune fiche enfant ne correspond : les créer dans les réglages.")
    if store.written_today() >= settings.daily_limit:
        raise HTTPException(429, f"Plafond de {settings.daily_limit} histoires par jour atteint.")

    band, user = story.brief(chosen, request.occasion, store.recent_titles(), date.today())
    try:
        written = story.write(story.system_prompt(band), user, band,
                              key=settings.openrouter_key, model=settings.model)
    except story.StoryError as exc:
        raise HTTPException(502, str(exc)) from exc

    entry = store.add_story(children=[c["id"] for c in chosen], occasion=request.occasion,
                            title=written.title, paragraphs=written.paragraphs,
                            model=settings.model, words=written.words)
    log.info("histoire %s écrite : %s (%d mots, %s)", entry.id, entry.title, entry.words, band.label)
    return _public(entry)


@app.post("/api/histoires/{story_id}/imprimer")
def print_story(story_id: str) -> dict:
    entry = store.story(story_id)
    if entry is None:
        raise HTTPException(404, "Histoire introuvable.")
    if not printing.acquire(blocking=False):
        raise HTTPException(409, "Un ticket est déjà en cours d'impression.")
    try:
        status = printer_status(fresh=True)
        if not status.ready:
            raise HTTPException(503, status.message)
        image = ticket.render_raster(entry.title, tuple(entry.paragraphs),
                                     _names(entry.children), date.fromisoformat(entry.created[:10]))
        try:
            printer.print_image(settings.printer_host, settings.printer_port, image)
        except printer.PrinterError as exc:
            raise HTTPException(503, str(exc)) from exc
        store.mark_printed(entry.id)
        return _public(store.story(entry.id))
    finally:
        printing.release()
