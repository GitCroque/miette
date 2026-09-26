"""Cherche et trouve.

Réutilise les polygones de `dot_to_dot` comme symboles : ce sont les mêmes
dessins que l'enfant relie ailleurs, donc elle les reconnaît déjà, et il n'y a
qu'un seul jeu de formes à maintenir.
"""

from __future__ import annotations

import random

from ..canvas import MARGIN, WIDTH_DOTS, Sheet
from .dot_to_dot import SHAPES

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
    if target not in SHAPES:
        raise KeyError(f"forme inconnue : {target}")
    total = cols * rows
    if not 1 <= occurrences <= total // 3:
        raise ValueError(
            f"{occurrences} cibles sur {total} cases : trop peu ou trop, "
            f"viser entre 1 et {total // 3}"
        )

    rng = random.Random(seed)
    others = [name for name in SHAPES if name != target]
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

    size = cell * 0.62
    for index, name in enumerate(grid):
        col, row = index % cols, index // cols
        # Décalage aléatoire pour casser l'alignement au cordeau, qui rend la
        # recherche mécanique et la planche triste.
        jitter_x = rng.uniform(-0.07, 0.07) * cell
        jitter_y = rng.uniform(-0.07, 0.07) * cell
        cx = left + col * cell + cell / 2 + jitter_x
        cy = top + row * cell + cell / 2 + jitter_y
        _draw_shape(sheet, name, cx, cy, size)

    return sheet, sorted(slots)


def _draw_shape(sheet: Sheet, name: str, cx: float, cy: float, size: float) -> None:
    """Dessine un polygone normalisé centré, sans déformer ses proportions."""
    points = SHAPES[name]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    scale = size / max(width, height)
    ox = cx - (min(xs) + width / 2) * scale
    oy = cy - (min(ys) + height / 2) * scale
    sheet.polygon([(ox + x * scale, oy + y * scale) for x, y in points], width=4)
