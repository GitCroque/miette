"""Données de Miette dans une base SQLite sur le volume : fiches enfants et carnet.

Les fiches (prénoms, doudous, crèche, copains) ne vivent que là, jamais dans
le dépôt. Le carnet garde chaque histoire écrite, imprimée ou non : il sert
à réimprimer sans repayer, à éviter les redites et à compter les histoires
du jour pour le plafond quotidien. Une histoire supprimée depuis l'historique
est seulement marquée : elle reste comptée dans le plafond du jour.

Les dessins et les jeux ont leur propre table. Un jeu ne garde que de quoi le
redessiner à l'identique (sujet et graine), un dessin de Claude garde son SVG :
l'aperçu et l'impression doivent montrer le même ticket.
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
    imprimee TEXT,
    favori INTEGER NOT NULL DEFAULT 0,
    supprimee TEXT,
    illustration TEXT,
    theme TEXT
);
CREATE TABLE IF NOT EXISTS dessins (
    id TEXT PRIMARY KEY,
    cree TEXT NOT NULL,
    genre TEXT NOT NULL,
    sujet TEXT NOT NULL,
    svg TEXT,
    graine INTEGER,
    imprime TEXT,
    favori INTEGER NOT NULL DEFAULT 0,
    supprime TEXT
);
"""

# Colonnes ajoutées après la création de chaque table : une base plus ancienne
# les reçoit à l'ouverture. Les dessins sont entrés dans l'historique le jour
# même de leur mise en service (2026-10-17).
LATER_COLUMNS = {
    "histoires": {
        "favori": "INTEGER NOT NULL DEFAULT 0",
        "supprimee": "TEXT",
        "illustration": "TEXT",
        "theme": "TEXT",
    },
    "dessins": {
        "favori": "INTEGER NOT NULL DEFAULT 0",
        "supprime": "TEXT",
    },
}

# Dessins écrits par Claude : ils coûtent comme une histoire et partagent son plafond.
PAID_KINDS = ("coloriage", "imagier")


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
    favorite: bool = False
    illustration: str | None = None
    theme: str | None = None


@dataclass(frozen=True)
class StoredDrawing:
    id: str
    created: str
    kind: str
    subject: str
    svg: str | None
    seed: int | None
    printed: str | None
    favorite: bool = False


class Store:
    def __init__(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(directory / "miette.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)
            for table, columns in LATER_COLUMNS.items():
                present = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}
                for column, definition in columns.items():
                    if column not in present:
                        self._db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
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
                  paragraphs: tuple[str, ...], model: str, words: int,
                  theme: str | None = None) -> StoredStory:
        story = StoredStory(
            id=uuid.uuid4().hex[:12],
            created=datetime.now().isoformat(timespec="seconds"),
            children=children, occasion=occasion, title=title,
            paragraphs=list(paragraphs), model=model, words=words, printed=None, theme=theme,
        )
        with self._lock:
            self._db.execute(
                "INSERT INTO histoires (id, cree, enfants, occasion, titre, paragraphes, modele, mots, theme) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (story.id, story.created, json.dumps(children, ensure_ascii=False), occasion,
                 title, json.dumps(story.paragraphs, ensure_ascii=False), model, words, theme),
            )
            self._db.commit()
        return story

    def mark_printed(self, story_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE histoires SET imprimee = ? WHERE id = ?",
                             (datetime.now().isoformat(timespec="seconds"), story_id))
            self._db.commit()

    def set_illustration(self, story_id: str, svg: str) -> None:
        with self._lock:
            self._db.execute("UPDATE histoires SET illustration = ? WHERE id = ?", (svg, story_id))
            self._db.commit()

    def set_favorite(self, story_id: str, favorite: bool) -> None:
        with self._lock:
            self._db.execute("UPDATE histoires SET favori = ? WHERE id = ?", (int(favorite), story_id))
            self._db.commit()

    def delete(self, story_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE histoires SET supprimee = ? WHERE id = ?",
                             (datetime.now().isoformat(timespec="seconds"), story_id))
            self._db.commit()

    def story(self, story_id: str) -> StoredStory | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM histoires WHERE id = ? AND supprimee IS NULL", (story_id,)
            ).fetchone()
        return _story(row) if row else None

    def printed(self, count: int = 5, favorites_only: bool = False) -> list[StoredStory]:
        """Histoires imprimées, la dernière imprimée (ou réimprimée) en tête."""
        where = "imprimee IS NOT NULL AND supprimee IS NULL" + (" AND favori = 1" if favorites_only else "")
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM histoires WHERE {where} ORDER BY imprimee DESC LIMIT ?", (count,)
            ).fetchall()
        return [_story(r) for r in rows]

    def recent_titles(self, count: int = 10) -> list[str]:
        with self._lock:
            rows = self._db.execute(
                "SELECT titre FROM histoires ORDER BY cree DESC LIMIT ?", (count,)
            ).fetchall()
        return [r["titre"] for r in rows]

    def written_today(self) -> int:
        """Histoires et dessins de Claude du jour, pour le plafond quotidien."""
        today = f"{datetime.now().date().isoformat()}%"
        marks = ", ".join("?" for _ in PAID_KINDS)
        with self._lock:
            stories = self._db.execute(
                "SELECT COUNT(*) AS n FROM histoires WHERE cree LIKE ?", (today,)
            ).fetchone()["n"]
            drawings = self._db.execute(
                f"SELECT COUNT(*) AS n FROM dessins WHERE cree LIKE ? AND genre IN ({marks})",
                (today, *PAID_KINDS),
            ).fetchone()["n"]
        return stories + drawings

    # Dessins et jeux

    def add_drawing(self, *, kind: str, subject: str, svg: str | None = None,
                    seed: int | None = None) -> StoredDrawing:
        drawing = StoredDrawing(
            id=uuid.uuid4().hex[:12], created=datetime.now().isoformat(timespec="seconds"),
            kind=kind, subject=subject, svg=svg, seed=seed, printed=None,
        )
        with self._lock:
            self._db.execute(
                "INSERT INTO dessins (id, cree, genre, sujet, svg, graine) VALUES (?, ?, ?, ?, ?, ?)",
                (drawing.id, drawing.created, kind, subject, svg, seed),
            )
            self._db.commit()
        return drawing

    def drawing(self, drawing_id: str) -> StoredDrawing | None:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM dessins WHERE id = ? AND supprime IS NULL", (drawing_id,)
            ).fetchone()
        return _drawing(row) if row else None

    def printed_drawings(self, count: int = 5, favorites_only: bool = False) -> list[StoredDrawing]:
        """Dessins et jeux imprimés, le dernier imprimé (ou réimprimé) en tête."""
        where = "imprime IS NOT NULL AND supprime IS NULL" + (" AND favori = 1" if favorites_only else "")
        with self._lock:
            rows = self._db.execute(
                f"SELECT * FROM dessins WHERE {where} ORDER BY imprime DESC LIMIT ?", (count,)
            ).fetchall()
        return [_drawing(r) for r in rows]

    def set_drawing_favorite(self, drawing_id: str, favorite: bool) -> None:
        with self._lock:
            self._db.execute("UPDATE dessins SET favori = ? WHERE id = ?", (int(favorite), drawing_id))
            self._db.commit()

    def delete_drawing(self, drawing_id: str) -> None:
        """Marque seulement : un coloriage supprimé reste compté dans le plafond du jour."""
        with self._lock:
            self._db.execute("UPDATE dessins SET supprime = ? WHERE id = ?",
                             (datetime.now().isoformat(timespec="seconds"), drawing_id))
            self._db.commit()

    def mark_drawing_printed(self, drawing_id: str) -> None:
        with self._lock:
            self._db.execute("UPDATE dessins SET imprime = ? WHERE id = ?",
                             (datetime.now().isoformat(timespec="seconds"), drawing_id))
            self._db.commit()

    def recent_subjects(self, kinds: tuple[str, ...], count: int = 12) -> list[str]:
        marks = ", ".join("?" for _ in kinds)
        with self._lock:
            rows = self._db.execute(
                f"SELECT sujet FROM dessins WHERE genre IN ({marks}) ORDER BY cree DESC LIMIT ?",
                (*kinds, count),
            ).fetchall()
        return [r["sujet"] for r in rows]


def _story(row: sqlite3.Row) -> StoredStory:
    return StoredStory(
        id=row["id"], created=row["cree"], children=json.loads(row["enfants"]),
        occasion=row["occasion"], title=row["titre"],
        paragraphs=json.loads(row["paragraphes"]), model=row["modele"],
        words=row["mots"], printed=row["imprimee"], favorite=bool(row["favori"]),
        illustration=row["illustration"], theme=row["theme"],
    )


def _drawing(row: sqlite3.Row) -> StoredDrawing:
    return StoredDrawing(
        id=row["id"], created=row["cree"], kind=row["genre"], subject=row["sujet"],
        svg=row["svg"], seed=row["graine"], printed=row["imprime"], favorite=bool(row["favori"]),
    )
