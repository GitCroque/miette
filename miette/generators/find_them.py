"""Cherche et trouve.

Les symboles portent les noms des formes des points à relier. Ils en étaient
les polygones jusqu'au 2026-11-01 ; ce sont depuis des dessins de MAI Image
2.6, plus vivants (décision de Julien), tirés une fois par
outils/dessins_fixes.py. Le nombre et la place des cibles restent tirés ici.
"""

from __future__ import annotations

import random

from ..canvas import MARGIN, WIDTH_DOTS, Sheet, load_drawing

# Nom de la forme et fichier de son dessin dans miette/dessins/cherche.
SYMBOLS = {
    "étoile": "etoile",
    "maison": "maison",
    "cœur": "coeur",
    "poisson": "poisson",
    "sapin": "sapin",
    "champignon": "champignon",
}

# Accord du nom au pluriel dans la consigne. Une enfant de quatre ans ne lit
# pas, mais l'adulte qui lit à voix haute, si.
PLURALS = {
    "étoile": "étoiles",
    "maison": "maisons",
    "cœur": "cœurs",
    "poisson": "poissons",
    "sapin": "sapins",
    "champignon": "champignons",
}


def render(target: str = "étoile", occurrences: int = 3, cols: int = 4,
           rows: int = 6, seed: int | None = None) -> tuple[Sheet, list[int]]:
    """Retourne la planche et les cases où se cache la cible, pour contrôle."""
    if target not in SYMBOLS:
        raise KeyError(f"forme inconnue : {target}")
    total = cols * rows
    if not 1 <= occurrences <= total // 3:
        raise ValueError(
            f"{occurrences} cibles sur {total} cases : trop peu ou trop, "
            f"viser entre 1 et {total // 3}"
        )

    rng = random.Random(seed)
    others = [name for name in SYMBOLS if name != target]
    grid = [rng.choice(others) for _ in range(total)]
    slots = rng.sample(range(total), occurrences)
    for slot in slots:
        grid[slot] = target

    cell = (WIDTH_DOTS - 2 * MARGIN) // cols
    left = (WIDTH_DOTS - cell * cols) // 2
    top = 150
    height = top + cell * rows + 30

    sheet = Sheet(height)
    plural = PLURALS.get(target, target)
    sheet.centered_text(16, "Cherche et trouve", 32)
    sheet.centered_text(62, f"Entoure les {occurrences} {plural}", 28)
    sheet.line(MARGIN, 124, WIDTH_DOTS - MARGIN, 124, 3)

    for index, name in enumerate(grid):
        col, row = index % cols, index // cols
        # Décalage aléatoire pour casser l'alignement au cordeau, qui rend la
        # recherche mécanique et la planche triste.
        jitter_x = rng.uniform(-0.07, 0.07) * cell
        jitter_y = rng.uniform(-0.07, 0.07) * cell
        cx = left + col * cell + cell / 2 + jitter_x
        cy = top + row * cell + cell / 2 + jitter_y
        art = load_drawing("cherche", SYMBOLS[name])
        sheet.picture(art, cx - art.width / 2, cy - art.height / 2)

    return sheet, sorted(slots)
