"""Carnet des histoires imprimées, une ligne JSON par histoire.

Sert à réimprimer une histoire que l'enfant redemande sans repayer sa
génération, et à compter les histoires du jour pour le plafond quotidien.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()


@dataclass(frozen=True)
class Entry:
    id: str
    at: str
    theme: str
    name: str
    pronoun: str
    title: str
    paragraphs: list[str]
    model: str
    words: int


class History:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "histoires.jsonl"

    def add(self, *, theme: str, name: str, pronoun: str, title: str,
            paragraphs: tuple[str, ...], model: str, words: int) -> Entry:
        entry = Entry(
            id=uuid.uuid4().hex[:12],
            at=datetime.now().isoformat(timespec="seconds"),
            theme=theme, name=name, pronoun=pronoun, title=title,
            paragraphs=list(paragraphs), model=model, words=words,
        )
        with _lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def all(self) -> list[Entry]:
        if not self.path.exists():
            return []
        entries = []
        with _lock, self.path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    entries.append(Entry(**json.loads(line)))
        return entries

    def recent(self, count: int = 5) -> list[Entry]:
        return list(reversed(self.all()[-count:]))

    def find(self, entry_id: str) -> Entry | None:
        return next((e for e in self.all() if e.id == entry_id), None)

    def count_today(self) -> int:
        today = datetime.now().date().isoformat()
        return sum(1 for e in self.all() if e.at.startswith(today))
