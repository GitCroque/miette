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
    assert old.title == "Ancienne" and old.favorite is False and old.illustration is None
    store.set_favorite("abc", True)
    assert [s.id for s in store.printed(favorites_only=True)] == ["abc"]
    new = store.add_story(children=["x"], occasion=None, title="Nouvelle",
                          paragraphs=("Texte.",), model="m", words=1)
    assert store.story(new.id).title == "Nouvelle"
    Store(tmp_path)  # une seconde ouverture ne réapplique rien


def test_illustrations_and_drawings(tmp_path):
    store = Store(tmp_path)
    story = store.add_story(children=["x"], occasion=None, title="Titre",
                            paragraphs=("Texte.",), model="m", words=1)
    store.set_illustration(story.id, "<svg/>")
    assert store.story(story.id).illustration == "<svg/>"

    coloring = store.add_drawing(kind="coloriage", subject="le chat", svg="<svg/>")
    store.add_drawing(kind="labyrinthe", subject="facile", seed=4)
    # L'histoire et le coloriage coûtent un appel au modèle, pas le labyrinthe.
    assert store.written_today() == 2
    assert store.recent_subjects(("coloriage", "imagier")) == ["le chat"]
    assert store.drawing(coloring.id).printed is None
    store.mark_drawing_printed(coloring.id)
    assert store.drawing(coloring.id).printed
    assert store.drawing("inconnu") is None


def test_the_first_drawings_table_is_migrated(tmp_path):
    db = sqlite3.connect(tmp_path / "miette.db")
    db.executescript("""
    CREATE TABLE dessins (id TEXT PRIMARY KEY, cree TEXT NOT NULL, genre TEXT NOT NULL,
        sujet TEXT NOT NULL, svg TEXT, graine INTEGER, imprime TEXT);
    INSERT INTO dessins VALUES ('d1', '2026-10-17T10:30:00', 'labyrinthe', 'facile', NULL, 4,
        '2026-10-17T10:31:00');
    """)
    db.commit()
    db.close()

    store = Store(tmp_path)
    assert store.drawing("d1").favorite is False
    store.set_drawing_favorite("d1", True)
    assert [d.id for d in store.printed_drawings(favorites_only=True)] == ["d1"]
    store.delete_drawing("d1")
    assert store.drawing("d1") is None and store.printed_drawings() == []
