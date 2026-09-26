"""Points à relier.

Les formes sont décrites directement par leurs points numérotés plutôt
qu'échantillonnées le long d'un contour : à dix ou douze points, un
échantillonnage régulier rate les angles caractéristiques et l'enfant obtient
une patate. Ici chaque point est un sommet voulu, donc la forme reliée est
toujours reconnaissable.

Coordonnées normalisées, origine en haut à gauche, x et y dans [0, 1], le
contour parcouru dans le sens horaire.
"""

from __future__ import annotations

import math

from ..canvas import MARGIN, WIDTH_DOTS, Sheet

# Distance entre le point et son numéro, et rayon occupé par un numéro à deux
# chiffres. Deux points plus proches que la somme des deux donnent des numéros
# qui se chevauchent : c'est ce que vérifie `overlapping_labels`.
LABEL_DISTANCE = 30
LABEL_RADIUS = 17

SHAPES: dict[str, list[tuple[float, float]]] = {
    "étoile": [
        (0.50, 0.00), (0.61, 0.33), (0.97, 0.35), (0.69, 0.57), (0.79, 0.95),
        (0.50, 0.72), (0.21, 0.95), (0.31, 0.57), (0.03, 0.35), (0.39, 0.33),
    ],
    "maison": [
        (0.50, 0.00), (0.93, 0.36), (0.93, 0.62), (0.93, 1.00), (0.62, 1.00),
        (0.62, 0.70), (0.38, 0.70), (0.38, 1.00), (0.07, 1.00), (0.07, 0.36),
    ],
    "cœur": [
        (0.50, 0.18), (0.63, 0.03), (0.84, 0.03), (0.98, 0.20), (0.96, 0.44),
        (0.72, 0.72), (0.50, 0.97), (0.28, 0.72), (0.04, 0.44), (0.02, 0.20),
        (0.16, 0.03), (0.37, 0.03),
    ],
    # Corps allongé et queue franchement fourchue : avec un corps presque rond
    # et une petite queue, le poisson se lisait comme une patate à encoche dès
    # qu'il servait de petit symbole dans le cherche et trouve.
    "poisson": [
        (1.00, 0.50), (0.82, 0.24), (0.58, 0.14), (0.36, 0.24), (0.26, 0.42),
        (0.00, 0.06), (0.00, 0.94), (0.26, 0.58), (0.36, 0.76), (0.58, 0.86),
        (0.82, 0.76),
    ],
    "sapin": [
        (0.50, 0.00), (0.74, 0.40), (0.60, 0.40), (0.92, 0.84), (0.58, 0.84),
        (0.58, 1.00), (0.42, 1.00), (0.42, 0.84), (0.08, 0.84), (0.40, 0.40),
        (0.26, 0.40),
    ],
    # Chapeau large et bombé, pied étroit : une première version au chapeau plat
    # se lisait comme un bonhomme, bras écartés.
    "champignon": [
        (0.50, 0.00), (0.74, 0.05), (0.93, 0.20), (1.00, 0.40), (0.60, 0.46),
        (0.58, 0.84), (0.70, 0.99), (0.30, 0.99), (0.42, 0.84), (0.40, 0.46),
        (0.00, 0.40), (0.07, 0.20), (0.26, 0.05),
    ],
}


def place(shape: str) -> tuple[list[tuple[float, float]], int, int]:
    """Position des points en points imprimante, plus le cadre de la planche."""
    points = SHAPES[shape]
    usable = WIDTH_DOTS - 2 * MARGIN
    label_room = LABEL_DISTANCE + LABEL_RADIUS
    span = usable - 2 * label_room
    top = 104
    # 60 points sous la forme : les numéros du bas débordent de LABEL_DISTANCE
    # plus leur propre hauteur, et la consigne finale doit rester lisible.
    height = top + span + 60 + 56
    placed = [
        (MARGIN + label_room + x * span, top + y * span) for x, y in points
    ]
    return placed, top, height


def label_positions(placed: list[tuple[float, float]]) -> list[tuple[float, float]]:
    cx = sum(p[0] for p in placed) / len(placed)
    cy = sum(p[1] for p in placed) / len(placed)
    return [_outward(x, y, cx, cy) for x, y in placed]


def overlapping_labels(shape: str) -> list[tuple[int, int, float]]:
    """Paires de numéros trop proches pour rester lisibles.

    Contrôle de qualité : une forme qui en renvoie ne doit pas être imprimée
    telle quelle, il faut écarter ses points.
    """
    placed, _, _ = place(shape)
    labels = label_positions(placed)
    clashes = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            distance = math.dist(labels[i], labels[j])
            if distance < 2 * LABEL_RADIUS:
                clashes.append((i + 1, j + 1, round(distance, 1)))
    return clashes


def render(shape: str = "étoile", show_outline: bool = False,
           title: str | None = None) -> Sheet:
    """Une planche de points à relier.

    `show_outline` trace le contour : sert à contrôler qu'une forme est bien
    dessinée, jamais pour l'impression destinée à l'enfant.
    """
    placed, _, height = place(shape)
    count = len(placed)

    sheet = Sheet(round(height))
    sheet.centered_text(16, title or f"Relie les points de 1 à {count}", 30)

    if show_outline:
        sheet.polygon(placed, width=3)

    for index, ((x, y), (lx, ly)) in enumerate(zip(placed, label_positions(placed)), 1):
        sheet.ellipse(x, y, 6, fill=True)
        sheet.text(lx, ly, str(index), 28, anchor="mm")

    sheet.centered_text(height - 44, "puis colorie ton dessin", 24)
    return sheet


def _outward(x: float, y: float, cx: float, cy: float) -> tuple[float, float]:
    """Pose le numéro à l'extérieur de la forme, dans l'axe centre vers point.

    Sans ça, les numéros tombent sur les traits que l'enfant va tracer et
    deviennent illisibles une fois le dessin relié.
    """
    dx, dy = x - cx, y - cy
    norm = math.hypot(dx, dy)
    if norm < 1e-6:
        return x, y - LABEL_DISTANCE
    return x + dx / norm * LABEL_DISTANCE, y + dy / norm * LABEL_DISTANCE
