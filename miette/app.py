"""Serveur web de Miette : une page pour le téléphone, une API pour imprimer."""

from __future__ import annotations

import logging
import threading
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, printer, story, ticket
from .history import Entry, History

STATIC = Path(__file__).parent / "static"

log = logging.getLogger("miette")
settings = config.load()
history = History(settings.data_dir)
# Une seule impression à la fois : deux appuis rapprochés ne doivent ni
# payer deux histoires ni entremêler deux tickets.
busy = threading.Lock()

app = FastAPI(title="Miette", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class StoryRequest(BaseModel):
    theme: str = Field("", max_length=120)
    prenom: str = Field("", max_length=40)
    pronom: Literal["elle", "il"] = "elle"
    rendu: Literal["raster", "texte"] | None = None


def _summary(entry: Entry) -> dict:
    return {"id": entry.id, "titre": entry.title, "prenom": entry.name, "date": entry.at}


def _print(title: str, paragraphs: tuple[str, ...], name: str, rendering: str) -> None:
    host, port = settings.printer_host, settings.printer_port
    if rendering == "texte":
        printer.print_with(host, port, lambda p: ticket.print_text(
            p, title, paragraphs, name, date.today()))
    else:
        image = ticket.render_raster(title, paragraphs, name, date.today())
        printer.print_image(host, port, image)


def _check_printer() -> None:
    state = printer.status(settings.printer_host, settings.printer_port)
    if not state.ready:
        raise HTTPException(503, state.message)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


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
    status = printer.status(settings.printer_host, settings.printer_port)
    return {
        "imprimante": status.message,
        "prete": status.ready,
        "papier_bas": status.paper_low,
        "cle": bool(settings.openrouter_key),
        "restantes": max(0, settings.daily_limit - history.count_today()),
        "histoires": [_summary(e) for e in history.recent()],
    }


@app.post("/api/histoire")
def new_story(request: StoryRequest) -> dict:
    if not busy.acquire(blocking=False):
        raise HTTPException(409, "Une histoire est déjà en cours d'impression.")
    try:
        if history.count_today() >= settings.daily_limit:
            raise HTTPException(429, f"Plafond de {settings.daily_limit} histoires par jour atteint.")
        _check_printer()
        theme = story.pick_theme(request.theme)
        name = " ".join(request.prenom.split())
        try:
            written = story.write(theme, name, request.pronom,
                                  key=settings.openrouter_key, model=settings.model)
        except story.StoryError as exc:
            raise HTTPException(502, str(exc)) from exc
        try:
            _print(written.title, written.paragraphs, name, request.rendu or settings.rendering)
        except printer.PrinterError as exc:
            raise HTTPException(503, str(exc)) from exc
        entry = history.add(theme=theme, name=name, pronoun=request.pronom,
                            title=written.title, paragraphs=written.paragraphs,
                            model=settings.model, words=written.words)
        log.info("histoire %s imprimée : %s (%d mots)", entry.id, entry.title, entry.words)
        return {**_summary(entry), "texte": written.text, "theme": theme}
    finally:
        busy.release()


@app.post("/api/reimprimer/{entry_id}")
def reprint(entry_id: str) -> dict:
    entry = history.find(entry_id)
    if entry is None:
        raise HTTPException(404, "Histoire introuvable.")
    if not busy.acquire(blocking=False):
        raise HTTPException(409, "Une histoire est déjà en cours d'impression.")
    try:
        _check_printer()
        try:
            _print(entry.title, tuple(entry.paragraphs), entry.name, settings.rendering)
        except printer.PrinterError as exc:
            raise HTTPException(503, str(exc)) from exc
        return _summary(entry)
    finally:
        busy.release()
