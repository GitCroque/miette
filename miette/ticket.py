"""Mise en page d'une histoire sur le ticket, en raster ou en mode texte.

Valeurs mesurées sur la TM-T88VI le 2026-09-26 : 512 points utiles, 180 dpi
dans les deux sens, 42 colonnes en Font A. Le texte composé en image reste
lisible dès 18 points et confortable à partir de 22.

Le raster compose toute la page avec Pillow, dans des polices libres
embarquées : Fredoka (ronde) pour le prénom et le titre, Gelasio (à
empattements, métriques de Georgia) pour le corps. Le mode texte utilise la
police de la machine : plus rapide, mais typographie imposée.
"""

from __future__ import annotations

import re
import textwrap
from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH = 512
MARGIN = 14
TEXT_WIDTH = WIDTH - 2 * MARGIN
COLUMNS = 42
THRESHOLD = 128

FONTS = Path(__file__).parent / "fonts"
ROUNDED, SERIF, SERIF_ITALIC = "Fredoka.ttf", "Gelasio.ttf", "Gelasio-Italic.ttf"

BODY_SIZE = 26
TITLE_SIZE = 42
NAME_MAX_SIZE = 96

MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre")


NBSP = "\u00a0"


def typeset(text: str) -> str:
    """Typographie française pour le raster : insécables et apostrophe courbe.

    Sans insécable, un « ! » ou un « » » peut se retrouver seul en début de
    ligne.
    """
    text = re.sub(r" ([!?:;»])", NBSP + r"\1", text)
    text = re.sub(r"« ", "«" + NBSP, text)
    return text.replace("'", "\u2019")


def plain(text: str) -> str:
    """Pour la police de la machine, qui n'a ni insécable ni apostrophe courbe."""
    return text.replace(NBSP, " ").replace("\u2019", "'")


def french_date(day: date) -> str:
    return f"{day.day} {MONTHS[day.month - 1]} {day.year}"


@lru_cache(maxsize=32)
def font(name: str, size: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    loaded = ImageFont.truetype(str(FONTS / name), size)
    if weight is not None:
        axes = loaded.get_variation_axes()
        loaded.set_variation_by_axes(
            [weight if i == 0 else axis["default"] for i, axis in enumerate(axes)]
        )
    return loaded


def wrap(text: str, face: ImageFont.FreeTypeFont, width: int) -> list[str]:
    """Coupe au mot près pour tenir dans `width` points."""
    lines: list[str] = []
    current = ""
    # Coupure sur les seules espaces ordinaires : str.split() couperait aussi
    # sur les insécables.
    for word in re.split(r"[ \t\n]+", text.strip()):
        candidate = f"{current} {word}".strip()
        if current and face.getlength(candidate) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def fit_size(text: str, name: str, weight: int, largest: int, width: int) -> int:
    size = largest
    while size > 24 and font(name, size, weight).getlength(text) > width:
        size -= 4
    return size


class _Page:
    """Feuille haute qu'on remplit de haut en bas, puis qu'on recadre."""

    def __init__(self) -> None:
        self.image = Image.new("L", (WIDTH, 6000), 255)
        self.draw = ImageDraw.Draw(self.image)
        self.y = 0

    def space(self, dots: int) -> None:
        self.y += dots

    def line(self, text: str, face: ImageFont.FreeTypeFont, height: int,
             center: bool = False) -> None:
        x = WIDTH / 2 if center else MARGIN
        self.draw.text((x, self.y), text, font=face, fill=0,
                       anchor="ma" if center else "la")
        self.y += height

    def rule(self, length: int = 180, thickness: int = 3) -> None:
        x0 = (WIDTH - length) // 2
        self.draw.rectangle([x0, self.y, x0 + length - 1, self.y + thickness - 1], fill=0)
        self.y += thickness

    def finish(self) -> Image.Image:
        cropped = self.image.crop((0, 0, WIDTH, self.y))
        return cropped.point(lambda v: 0 if v < THRESHOLD else 255, mode="1")


def render_raster(title: str, paragraphs: tuple[str, ...], name: str,
                  day: date) -> Image.Image:
    page = _Page()
    page.space(6)

    if name:
        page.line("Une histoire pour", font(SERIF_ITALIC, 24), 34, center=True)
        size = fit_size(name, ROUNDED, 700, NAME_MAX_SIZE, TEXT_WIDTH)
        page.line(name, font(ROUNDED, size, 700), round(size * 1.15), center=True)
        page.space(10)

    page.rule()
    page.space(26)

    title_face = font(ROUNDED, TITLE_SIZE, 600)
    for line in wrap(typeset(title), title_face, TEXT_WIDTH):
        page.line(line, title_face, round(TITLE_SIZE * 1.18), center=True)
    page.space(22)

    body_face = font(SERIF, BODY_SIZE)
    body_height = round(BODY_SIZE * 1.42)
    for index, paragraph in enumerate(paragraphs):
        if index:
            page.space(body_height // 2)
        for line in wrap(typeset(paragraph), body_face, TEXT_WIDTH):
            page.line(line, body_face, body_height)

    page.space(22)
    page.rule(80, 2)
    page.space(14)
    page.line(f"Miette, le {french_date(day)}", font(SERIF_ITALIC, 20), 28, center=True)
    return page.finish()


def print_text(printer, title: str, paragraphs: tuple[str, ...], name: str,
               day: date) -> None:
    """Même ticket en mode texte ESC/POS, avec la police de la machine."""
    if name:
        printer.set_with_default(align="center")
        printer.text("Une histoire pour\n")
        printer.set_with_default(align="center", bold=True,
                                 double_width=True, double_height=True)
        printer.text(name + "\n\n")

    printer.set_with_default(align="center", bold=True, double_height=True)
    for line in textwrap.wrap(plain(title), COLUMNS):
        printer.text(line + "\n")
    printer.text("\n")

    printer.set_with_default()
    for paragraph in paragraphs:
        for line in textwrap.wrap(plain(paragraph), COLUMNS):
            printer.text(line + "\n")
        printer.text("\n")

    printer.set_with_default(align="center", font="b")
    printer.text(f"Miette, le {french_date(day)}\n")
    printer.set_with_default()
