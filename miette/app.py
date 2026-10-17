"""Serveur web de Miette : une page pour le téléphone, une API pour imprimer.

Déroulé décidé le 2026-09-26 : choisir l'enfant (ou les deux), Surprise ou
une occasion, lire l'aperçu, puis imprimer ou en demander une autre. Depuis le
2026-10-17, même déroulé pour les coloriages (par thème, avec le nom du sujet
en grand : l'ancien imagier y est fondu) et les jeux (labyrinthe, points à
relier, cherche et trouve), et chaque histoire peut recevoir son illustration.
"""

from __future__ import annotations

import io
import logging
import random
import threading
import time
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from PIL import Image

from . import claude, config, drawing, printer, story, ticket
from .generators import dot_to_dot, find_them, maze
from .store import Store, StoredDrawing, StoredStory

STATIC = Path(__file__).parent / "static"
FONTS = Path(__file__).parent / "fonts"
MAX_CHILDREN = 6

ACTIVITIES = {
    "coloriage": "Coloriage",
    "labyrinthe": "Labyrinthe",
    "points": "Points à relier",
    "cherche": "Cherche et trouve",
}
# Les imagiers imprimés avant leur fusion dans le coloriage gardent leur nom.
KIND_LABELS = {**ACTIVITIES, "imagier": "Imagier"}
# Le plus simple d'abord : les enfants ont 2 ans à l'automne 2026.
MAZE_LEVELS = list(maze.LEVELS)

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


class DrawingRequest(BaseModel):
    genre: Literal["coloriage", "labyrinthe", "points", "cherche"]
    niveau: Literal["tout-petit", "facile", "moyen", "costaud"] | None = None
    categorie: Literal["animaux", "vehicules", "maison", "nature", "a-manger"] | None = None


def _names(ids: list[str]) -> str:
    by_id = {c["id"]: c["prenom"] for c in store.children()}
    names = [by_id.get(i, "") for i in ids]
    names = [n for n in names if n]
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " et " + names[-1]


def _public(entry: StoredStory) -> dict:
    return {
        "type": "histoire",
        "id": entry.id,
        "titre": entry.title,
        "texte": "\n\n".join(entry.paragraphs),
        "pour": _names(entry.children),
        "occasion": entry.occasion,
        "date": entry.created,
        "imprimee": entry.printed,
        "favori": entry.favorite,
        "illustration": entry.illustration is not None,
    }


def _drawing_title(entry: StoredDrawing) -> str:
    if entry.kind == "labyrinthe":
        return f"Labyrinthe {entry.subject}"
    return f"{KIND_LABELS[entry.kind]} : {entry.subject}"


def _public_drawing(entry: StoredDrawing) -> dict:
    return {
        "type": "dessin",
        "id": entry.id,
        "genre": entry.kind,
        "sujet": entry.subject,
        "titre": _drawing_title(entry),
        "date": entry.created,
        "imprimee": entry.printed,
        "favori": entry.favorite,
    }


def _history(count: int, favorites_only: bool = False) -> list[dict]:
    """Histoires, dessins et jeux imprimés, mêlés, le dernier imprimé en tête."""
    items = [_public(e) for e in store.printed(count, favorites_only)]
    items += [_public_drawing(e) for e in store.printed_drawings(count, favorites_only)]
    items.sort(key=lambda item: item["imprimee"], reverse=True)
    return items[:count]


def _picture(svg: str) -> Image.Image:
    return drawing.trim(drawing.render(svg, ticket.TEXT_WIDTH))


def _drawing_ticket(entry: StoredDrawing) -> Image.Image:
    """Le ticket complet, recomposé à l'identique pour l'aperçu comme pour l'impression."""
    day = date.fromisoformat(entry.created[:10])
    if entry.kind in ("coloriage", "imagier"):
        return ticket.render_coloring(_picture(entry.svg), entry.subject, day)
    if entry.kind == "labyrinthe":
        sheet = maze.render(entry.subject, seed=entry.seed)
    elif entry.kind == "points":
        sheet = dot_to_dot.render(entry.subject)
    else:
        sheet, _ = find_them.render(entry.subject, seed=entry.seed)
    return ticket.render_game(sheet.to_bilevel(), day)


def _png(image: Image.Image, cache: str = "no-store") -> Response:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": cache})


def _print(image: Image.Image) -> None:
    """Imprime un ticket, un seul à la fois, après avoir vérifié la machine."""
    if not printing.acquire(blocking=False):
        raise HTTPException(409, "Un ticket est déjà en cours d'impression.")
    try:
        status = printer_status(fresh=True)
        if not status.ready:
            raise HTTPException(503, status.message)
        try:
            printer.print_image(settings.printer_host, settings.printer_port, image)
        except printer.PrinterError as exc:
            raise HTTPException(503, str(exc)) from exc
    finally:
        printing.release()


def _check_daily_limit() -> None:
    if store.written_today() >= settings.daily_limit:
        raise HTTPException(429, f"Plafond de {settings.daily_limit} histoires et dessins par jour atteint.")


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
        "cle": bool(settings.anthropic_key),
        "restantes": max(0, settings.daily_limit - store.written_today()),
        "enfants": [{"id": c["id"], "prenom": c["prenom"], "age": story.age_label(c, date.today())}
                    for c in store.children()],
        "occasions": story.OCCASIONS,
        "activites": ACTIVITIES,
        "categories": {key: label for key, (label, _) in drawing.CATEGORIES.items()},
        "niveaux": MAZE_LEVELS,
        "derniere": _public(last[0]) if last else None,
        "favoris": _history(3, favorites_only=True),
    }


@app.get("/api/enfants")
def children() -> list[dict]:
    return store.children()


@app.put("/api/enfants")
def save_children(children: list[Child]) -> list[dict]:
    if len(children) > MAX_CHILDREN:
        raise HTTPException(422, f"{MAX_CHILDREN} fiches au plus.")
    return store.save_children([c.model_dump() for c in children])


@app.get("/api/historique")
def history(favoris: bool = False) -> list[dict]:
    """L'historique : tout ce qui est sorti de l'imprimante, jamais les aperçus écartés."""
    return _history(500, favorites_only=favoris)


@app.get("/api/historique/{item_id}")
def history_item(item_id: str) -> dict:
    if (entry := store.story(item_id)) is not None:
        return _public(entry)
    if (drawn := store.drawing(item_id)) is not None:
        return _public_drawing(drawn)
    raise HTTPException(404, "Introuvable dans l'historique.")


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
    _check_daily_limit()

    band, user = story.brief(chosen, request.occasion, store.recent_titles(), date.today())
    try:
        written = story.write(story.system_prompt(band), user, band,
                              key=settings.anthropic_key, model=settings.model)
    except claude.ClaudeError as exc:
        raise HTTPException(502, str(exc)) from exc

    entry = store.add_story(children=[c["id"] for c in chosen], occasion=request.occasion,
                            title=written.title, paragraphs=written.paragraphs,
                            model=settings.model, words=written.words)
    log.info("histoire %s écrite : %s (%d mots, %s)", entry.id, entry.title, entry.words, band.label)
    return _public(entry)


@app.post("/api/histoires/{story_id}/illustration")
def illustrate_story(story_id: str) -> dict:
    """Dessine l'illustration d'une histoire déjà écrite, une fois pour toutes."""
    entry = store.story(story_id)
    if entry is None:
        raise HTTPException(404, "Histoire introuvable.")
    if entry.illustration is None:
        try:
            svg = drawing.draw(drawing.illustration_prompt(entry.title, entry.paragraphs),
                               key=settings.anthropic_key, model=settings.model)
        except claude.ClaudeError as exc:
            raise HTTPException(502, str(exc)) from exc
        store.set_illustration(entry.id, svg)
        log.info("histoire %s illustrée", entry.id)
    return _public(store.story(entry.id))


@app.get("/api/histoires/{story_id}/illustration.png", include_in_schema=False)
def story_illustration(story_id: str) -> Response:
    entry = store.story(story_id)
    if entry is None or entry.illustration is None:
        raise HTTPException(404, "Pas d'illustration.")
    # Une illustration ne change plus une fois dessinée.
    return _png(_picture(entry.illustration), "private, max-age=604800, immutable")


@app.post("/api/histoires/{story_id}/imprimer")
def print_story(story_id: str) -> dict:
    entry = store.story(story_id)
    if entry is None:
        raise HTTPException(404, "Histoire introuvable.")
    picture = _picture(entry.illustration) if entry.illustration else None
    _print(ticket.render_raster(entry.title, tuple(entry.paragraphs), _names(entry.children),
                                date.fromisoformat(entry.created[:10]), picture))
    store.mark_printed(entry.id)
    return _public(store.story(entry.id))


@app.post("/api/dessins")
def make_drawing(request: DrawingRequest) -> dict:
    """Prépare un dessin ou un jeu en aperçu, sans l'imprimer."""
    kind = request.genre
    rng = random.Random()
    if kind == "coloriage":
        _check_daily_limit()
        subject = drawing.pick_subject(store.recent_subjects(("coloriage", "imagier")), request.categorie, rng)
        try:
            svg = drawing.draw(drawing.coloring_prompt(subject), key=settings.anthropic_key, model=settings.model)
        except claude.ClaudeError as exc:
            raise HTTPException(502, str(exc)) from exc
        entry = store.add_drawing(kind=kind, subject=subject, svg=svg)
    elif kind == "labyrinthe":
        entry = store.add_drawing(kind=kind, subject=request.niveau or MAZE_LEVELS[0],
                                  seed=rng.randrange(1 << 31))
    else:
        shapes = list(dot_to_dot.SHAPES)
        recent = store.recent_subjects((kind,), count=len(shapes) - 1)
        subject = rng.choice([s for s in shapes if s not in recent] or shapes)
        entry = store.add_drawing(kind=kind, subject=subject, seed=rng.randrange(1 << 31))
    log.info("%s %s préparé : %s", kind, entry.id, entry.subject)
    return _public_drawing(entry)


@app.get("/api/dessins/{drawing_id}.png", include_in_schema=False)
def drawing_image(drawing_id: str) -> Response:
    entry = store.drawing(drawing_id)
    if entry is None:
        raise HTTPException(404, "Dessin introuvable.")
    return _png(_drawing_ticket(entry), "private, max-age=604800, immutable")


@app.get("/api/dessins/{drawing_id}")
def read_drawing(drawing_id: str) -> dict:
    entry = store.drawing(drawing_id)
    if entry is None:
        raise HTTPException(404, "Dessin introuvable.")
    return _public_drawing(entry)


@app.post("/api/dessins/{drawing_id}/favori")
def set_drawing_favorite(drawing_id: str, body: Favorite) -> dict:
    if store.drawing(drawing_id) is None:
        raise HTTPException(404, "Dessin introuvable.")
    store.set_drawing_favorite(drawing_id, body.favori)
    return _public_drawing(store.drawing(drawing_id))


@app.delete("/api/dessins/{drawing_id}")
def delete_drawing(drawing_id: str) -> dict:
    if store.drawing(drawing_id) is None:
        raise HTTPException(404, "Dessin introuvable.")
    store.delete_drawing(drawing_id)
    return {"ok": True}


@app.post("/api/dessins/{drawing_id}/imprimer")
def print_drawing(drawing_id: str) -> dict:
    entry = store.drawing(drawing_id)
    if entry is None:
        raise HTTPException(404, "Dessin introuvable.")
    _print(_drawing_ticket(entry))
    store.mark_drawing_printed(entry.id)
    return _public_drawing(store.drawing(entry.id))
