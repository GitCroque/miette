"""Labyrinthe parfait, taillé pour le format vertical du ticket.

Un labyrinthe « parfait » est un arbre couvrant : il existe exactement un
chemin entre deux cellules, donc jamais de boucle et jamais d'impasse
infranchissable. La solvabilité est en outre vérifiée par un parcours en
largeur avant de rendre l'image, parce qu'un labyrinthe sans issue imprimé
devant une enfant qui attend, c'est le genre de bug qu'on ne rattrape pas.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from ..canvas import MARGIN, WIDTH_DOTS, Sheet

NORTH, EAST, SOUTH, WEST = 1, 2, 4, 8
OPPOSITE = {NORTH: SOUTH, SOUTH: NORTH, EAST: WEST, WEST: EAST}
STEP = {NORTH: (0, -1), SOUTH: (0, 1), EAST: (1, 0), WEST: (-1, 0)}

# Grilles par âge. Au-delà de 7 colonnes les cellules passent sous 10 mm et
# deviennent pénibles à suivre au crayon.
LEVELS = {
    "tout-petit": (4, 6),
    "facile": (5, 8),
    "moyen": (6, 11),
    "costaud": (7, 14),
}


@dataclass
class Maze:
    cols: int
    rows: int
    walls: list[list[int]]
    path_length: int

    def has_wall(self, col: int, row: int, side: int) -> bool:
        return bool(self.walls[row][col] & side)


def generate(cols: int, rows: int, seed: int | None = None) -> Maze:
    """Creuse un labyrinthe parfait par exploration en profondeur."""
    rng = random.Random(seed)
    walls = [[NORTH | EAST | SOUTH | WEST for _ in range(cols)] for _ in range(rows)]
    visited = [[False] * cols for _ in range(rows)]

    stack = [(0, 0)]
    visited[0][0] = True
    while stack:
        col, row = stack[-1]
        options = []
        for side, (dc, dr) in STEP.items():
            nc, nr = col + dc, row + dr
            if 0 <= nc < cols and 0 <= nr < rows and not visited[nr][nc]:
                options.append((side, nc, nr))
        if not options:
            stack.pop()
            continue
        side, nc, nr = rng.choice(options)
        walls[row][col] &= ~side
        walls[nr][nc] &= ~OPPOSITE[side]
        visited[nr][nc] = True
        stack.append((nc, nr))

    length = _shortest_path(cols, rows, walls)
    if length is None:
        raise RuntimeError("labyrinthe sans solution, la génération est cassée")
    return Maze(cols=cols, rows=rows, walls=walls, path_length=length)


def _shortest_path(cols: int, rows: int, walls: list[list[int]]) -> int | None:
    """Longueur du chemin du coin haut gauche au coin bas droit, en cellules."""
    start, goal = (0, 0), (cols - 1, rows - 1)
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        (col, row), distance = queue.popleft()
        if (col, row) == goal:
            return distance
        for side, (dc, dr) in STEP.items():
            if walls[row][col] & side:
                continue
            nc, nr = col + dc, row + dr
            if 0 <= nc < cols and 0 <= nr < rows and (nc, nr) not in seen:
                seen.add((nc, nr))
                queue.append(((nc, nr), distance + 1))
    return None


def render(level: str = "facile", seed: int | None = None,
           title: str = "Le labyrinthe") -> Sheet:
    cols, rows = LEVELS[level]
    maze = generate(cols, rows, seed)

    stroke = 4
    cell = (WIDTH_DOTS - 2 * MARGIN) // cols
    grid_width = cell * cols
    left = (WIDTH_DOTS - grid_width) // 2
    title_height = 78
    top = title_height
    height = top + cell * rows + 56

    sheet = Sheet(height)
    sheet.centered_text(18, title, 34)

    for row in range(rows):
        for col in range(cols):
            x0 = left + col * cell
            y0 = top + row * cell
            x1, y1 = x0 + cell, y0 + cell
            # Entrée en haut à gauche, sortie en bas à droite : on retire ces
            # deux murs du tracé plutôt que du modèle, pour que la vérification
            # de solvabilité reste faite sur un labyrinthe clos.
            entrance = row == 0 and col == 0
            exit_ = row == rows - 1 and col == cols - 1
            if maze.has_wall(col, row, NORTH) and not entrance:
                sheet.line(x0, y0, x1, y0, stroke)
            if maze.has_wall(col, row, WEST):
                sheet.line(x0, y0, x0, y1, stroke)
            if maze.has_wall(col, row, EAST) and col == cols - 1:
                sheet.line(x1, y0, x1, y1, stroke)
            if maze.has_wall(col, row, SOUTH) and not exit_:
                sheet.line(x0, y1, x1, y1, stroke)

    # Repères : un rond plein à l'entrée, une étoile à la sortie.
    sheet.ellipse(left + cell / 2, top + cell / 2, cell * 0.18, fill=True)
    _star(sheet, left + grid_width - cell / 2, top + cell * rows - cell / 2, cell * 0.30)

    baseline = top + cell * rows + 14
    sheet.centered_text(baseline, f"{maze.path_length} cases à traverser", 22)
    return sheet


def _star(sheet: Sheet, cx: float, cy: float, radius: float) -> None:
    import math

    points = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        reach = radius if index % 2 == 0 else radius * 0.45
        points.append((cx + reach * math.cos(angle), cy + reach * math.sin(angle)))
    sheet.polygon(points, width=3)
