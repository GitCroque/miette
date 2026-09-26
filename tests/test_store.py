import sqlite3

from miette.store import Store

OLD_SCHEMA = """
CREATE TABLE reglages (cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE histoires (
    id TEXT PRIMARY KEY, cree TEXT NOT NULL, enfants TEXT NOT NULL, occasion TEXT,
    titre TEXT NOT NULL, paragraphes TEXT NOT NULL, modele TEXT NOT NULL,
    mots INTEGER NOT NULL, imprimee TEXT
);
INSERT INTO histoires VALUES ('abc', '2026-09-26T19:00:00', '["x"]', NULL, 'Ancienne',
    '["Un paragraphe."]', 'm', 2, '2026-09-26T19:01:00');
"""


def test_a_first_version_database_is_migrated(tmp_path):
    db = sqlite3.connect(tmp_path / "miette.db")
    db.executescript(OLD_SCHEMA)
    db.commit()
    db.close()

    store = Store(tmp_path)
    old = store.story("abc")
    assert old.title == "Ancienne" and old.favorite is False
    store.set_favorite("abc", True)
    assert [s.id for s in store.printed(favorites_only=True)] == ["abc"]
    new = store.add_story(children=["x"], occasion=None, title="Nouvelle",
                          paragraphs=("Texte.",), model="m", words=1)
    assert store.story(new.id).title == "Nouvelle"
    Store(tmp_path)  # une seconde ouverture ne réapplique rien
