"""Dessine les icônes de l'app web (écran d'accueil de l'iPhone, manifeste).

Un ticket blanc qui sort, sur fond orangé, et trois miettes qui tombent.

    python3 outils/icones.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

STATIC = Path(__file__).resolve().parent.parent / "miette" / "static"
BACKGROUND = (217, 96, 59)
PAPER = (255, 250, 242)
LINES = (230, 216, 195)


def draw(size: int) -> Image.Image:
    scale = 4
    s = size * scale
    image = Image.new("RGB", (s, s), BACKGROUND)
    d = ImageDraw.Draw(image)
    left, right, top, bottom = 0.27 * s, 0.73 * s, 0.14 * s, 0.70 * s
    tooth = (right - left) / 6
    outline = [(left, top), (right, top), (right, bottom)]
    for i in range(6):
        x = right - (i + 0.5) * tooth
        outline += [(x, bottom + tooth * 0.55), (right - (i + 1) * tooth, bottom)]
    d.polygon(outline, fill=PAPER)
    bar = 0.035 * s
    for i, width in enumerate((0.34, 0.26, 0.30)):
        y = top + 0.12 * s + i * 0.1 * s
        d.rounded_rectangle([left + 0.06 * s, y, left + 0.06 * s + width * s, y + bar], radius=bar / 2, fill=LINES)
    for cx, cy, r in ((0.40, 0.84, 0.028), (0.53, 0.89, 0.022), (0.62, 0.82, 0.018)):
        d.ellipse([(cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s], fill=PAPER)
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    for size in (180, 512):
        draw(size).save(STATIC / f"icon-{size}.png")


if __name__ == "__main__":
    main()
