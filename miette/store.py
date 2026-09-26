"""Données de Miette dans une base SQLite sur le volume : fiches enfants et carnet.

Les fiches (prénoms, doudous, crèche, copains) ne vivent que là, jamais dans
le dépôt. Le carnet garde chaque histoire écrite, imprimée ou non : il sert
à réimprimer sans repayer, à éviter les redites et à compter les histoires
du jour pour le plafond quotidien.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS reglages (
    cle TEXT PRIMARY KEY,
    valeur TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS histoires (
    id TEXT PRIMARY KEY,
    cree TEXT NOT NULL,
    enfants TEXT NOT NULL,
    occasion TEXT,
    titre TEXT NOT NULL,
    paragraphes TEXT NOT NULL,
    modele TEXT NOT NULL,
    mots INTEGER NOT NULL,
    imprimee TEXT
);
"""


@dataclass(frozen=True)
class StoredStory:
    id: str
    created: str
    children: list[str]
    occasion: str | None
    title: str
    paragraphs: list[str]
    model: str
    words: int
    printed: str | None


class Store:
    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(directory / "miette.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            self._db.commit()

    # Fiches enfants

    def children(self) -> list[dict]:
        with self._lock:
            row = self._db.execute("SELECT valeur FROM reglages WHERE cle = 'enfants'").fetchone()
        return json.loads(row["valeur"]) if row else []

    def save_children(self, children: list[dict]) -> list[dict]:
        for child in children:
            child["id"] = child.get("id") or uuid.uuid4().hex[:8]
        with self._lock:
            self._db.execute(
                "INSERT INTO reglages (cle, valeur) VALUES ('enfants', ?) "
                "ON CONFLICT(cle) DO UPDATE SET valeur = excluded.valeur",
                (json.dumps(children, ensure_ascii=False),),
            )
            self._db.commit()
        return children

    # Carnet

    def add_story(self, *, children: list[str], occasion: str | None, title: str,
                  paragraphs: tuple[str, ...], model: str, words: int) -> StoredStory:
        story = StoredStory(
            id=uuid.uuid4().hex[:12],
            created=datetime.now().isoformat(timespec="seconds"),
            children=children, occasion=occasion, title=title,
            paragraphs=list(paragraphs), model=model, words=words, printed=None,
        )
        with self._lock:
            self._db.execute(
                "INSERT INTO histoires VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (story.id, story.created, json.dumps(children, ensure_ascii=False), occasion,
                 title, json.dumps(story.paragraphs, ensure_ascii=False), model, words),
            )
            self._db.commit()
        return story

    def mark_printed(self, story_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE histoires SET imprimee = ? WHERE id = ?",
                             (datetime.now().isoformat(timespec="seconds"), story_id))
            self._db.commit()

    def story(self, story_id: str) -> StoredStory | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM histoires WHERE id = ?", (story_id,)).fetchone()
        return _story(row) if row else None

    def printed(self, count: int = 5) -> list[StoredStory]:
        with self._lock:
            rows = self._db.execute(
                "SELECT * FROM histoires WHERE imprimee IS NOT NULL ORDER BY imprimee DESC LIMIT ?",
                (count,),
            ).fetchall()
        return [_story(r) for r in rows]

    def recent_titles(self, count: int = 10) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT titre FROM histoires ORDER BY cree DESC LIMIT ?", (count,)
            ).fetchall()
        return [r["titre"] for r in rows]

    def written_today(self) -> int:
        today = datetime.now().date().isoformat()
        with self._lock:
            row = self._db.execute(
                "SELECT COUNT(*) AS n FROM histoires WHERE cree LIKE ?", (f"{today}%",)
            ).fetchone()
        return row["n"]


def _story(row: sqlite3.Row) -> StoredStory:
    return StoredStory(
        id=row["id"], created=row["cree"], children=json.loads(row["enfants"]),
        occasion=row["occasion"], title=row["titre"],
        paragraphs=json.loads(row["paragraphes"]), model=row["modele"],
        words=row["mots"], printed=row["imprimee"],
    )
