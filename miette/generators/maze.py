"""Labyrinthe parfait, taillé pour le format vertical du ticket.

Un labyrinthe « parfait » est un arbre couvrant : il existe exactement un
chemin entre deux cellules, donc jamais de boucle et jamais d'impasse
infranchissable. La solvabilité est en outre vérifiée par un parcours en
largeur avant de rendre l'image, parce qu'un labyrinthe sans issue imprimé
devant une enfant qui attend, c'est le genre de bug qu'on ne rattrape pas.

Depuis le 2026-11-01 (décision de Julien), un personnage attend à l'entrée et
son but à la sortie, avec la consigne que l'adulte lit à voix haute : « Aide
le hérisson à retrouver sa pomme ». Les dessins viennent de MAI Image 2.6,
tirés une fois (outils/dessins_fixes.py) : la grille reste calculée ici, le
jeu reste instantané et ne coûte rien.
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass

from ..canvas import MARGIN, WIDTH_DOTS, Sheet, load_drawing

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


# Personnage, son nom, son but, et le but tel que la consigne le dit. Le tirage
# suit la graine du labyrinthe : ajouter une paire change le personnage d'une
# réimpression ancienne, jamais sa grille.
PAIRS = (
    ("herisson", "le hérisson", "pomme", "sa pomme"),
    ("lapin", "le lapin", "carotte", "sa carotte"),
    ("souris", "la souris", "fromage", "son fromage"),
    ("abeille", "l'abeille", "fleur", "sa fleur"),
    ("chien", "le chien", "os", "son os"),
    ("ecureuil", "l'écureuil", "pin", "sa pomme de pin"),
    ("ours", "l'ours", "miel", "son pot de miel"),
    ("singe", "le singe", "banane", "sa banane"),
    ("chat", "le chat", "pelote", "sa pelote de laine"),
    ("poussin", "le poussin", "poule", "sa maman"),
    ("escargot", "l'escargot", "salade", "sa salade"),
)

TITLE_SIZE = 28
LINE_HEIGHT = 36
GAP = 8


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


def pair_for(seed: int | None) -> tuple[str, str, str, str]:
    return PAIRS[random.Random(seed).randrange(len(PAIRS))]


def _wrap(sheet: Sheet, text: str, size: int, width: float) -> list[str]:
    lines, current = [], ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if current and sheet.text_width(trial, size) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + [current] if current else lines


def render(level: str = "facile", seed: int | None = None, title: str | None = None) -> Sheet:
    cols, rows = LEVELS[level]
    maze = generate(cols, rows, seed)
    hero_file, hero, goal_file, goal = pair_for(seed)
    hero_art = load_drawing("labyrinthe", hero_file)
    goal_art = load_drawing("labyrinthe", goal_file)

    stroke = 4
    cell = (WIDTH_DOTS - 2 * MARGIN) // cols
    grid_width = cell * cols
    left = (WIDTH_DOTS - grid_width) // 2

    # Le personnage juste au-dessus de l'entrée, la consigne à sa droite.
    hero_x = max(MARGIN, round(left + cell / 2 - hero_art.width / 2))
    text_x = hero_x + hero_art.width + 14
    lines = _wrap(Sheet(1), title or f"Aide {hero} à retrouver {goal}", TITLE_SIZE,
                  WIDTH_DOTS - MARGIN - text_x)
    band = max(hero_art.height, len(lines) * LINE_HEIGHT)
    top = MARGIN + band + GAP
    bottom = top + cell * rows
    height = bottom + GAP + goal_art.height + MARGIN

    sheet = Sheet(height)
    sheet.picture(hero_art, hero_x, top - GAP - hero_art.height)
    text_top = MARGIN + (band - len(lines) * LINE_HEIGHT) / 2
    for index, line in enumerate(lines):
        sheet.text(text_x, text_top + index * LINE_HEIGHT, line, TITLE_SIZE)

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

    # Le but juste sous la sortie, la longueur du chemin à sa gauche.
    goal_x = min(WIDTH_DOTS - MARGIN - goal_art.width,
                 round(left + grid_width - cell / 2 - goal_art.width / 2))
    sheet.picture(goal_art, goal_x, bottom + GAP)
    sheet.text(left, bottom + GAP + goal_art.height / 2, f"{maze.path_length} cases à traverser",
               22, anchor="lm")
    return sheet
