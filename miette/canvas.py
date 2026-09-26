"""Socle de rendu des tickets Miette.

Les contraintes de l'imprimante thermique commandent tout le reste :

- 1 bit strict, noir ou blanc, aucun niveau de gris ;
- 203 dpi, soit 8 points par millimètre ;
- 576 points utiles en largeur sur un rouleau de 80 mm.

On dessine en niveaux de gris à une échelle supérieure, puis on réduit et on
seuille. Dessiner directement en 1 bit crénellerait les courbes. Le tramage
type Floyd-Steinberg est volontairement exclu : il est fait pour la photo et
transforme un trait propre en nuage de points.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH_DOTS = 576
DOTS_PER_MM = 8
MARGIN = 16
SUPERSAMPLE = 4
THRESHOLD = 128
MIN_STROKE = 3

WHITE = 255
BLACK = 0

# Cherchées dans l'ordre. Les premières sont sur le Mac de développement, les
# DejaVu seront celles du conteneur Linux. Le repli Pillow évite un crash mais
# donne un rendu médiocre : si on y arrive, c'est qu'il faut embarquer une
# police dans l'image Docker.
FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
)


def mm(value: float) -> int:
    """Convertit des millimètres en points imprimante."""
    return round(value * DOTS_PER_MM)


def load_font(size_dots: int) -> ImageFont.FreeTypeFont:
    """Charge une police à la taille demandée, exprimée en points finaux."""
    scaled = size_dots * SUPERSAMPLE
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, scaled)
    return ImageFont.load_default(size=scaled)


class Sheet:
    """Une zone de dessin à la largeur du ticket.

    L'appelant travaille toujours en points finaux : la mise à l'échelle du
    suréchantillonnage est interne, pour qu'aucun générateur n'ait à y penser.
    """

    def __init__(self, height_dots: int, width_dots: int = WIDTH_DOTS) -> None:
        self.width = width_dots
        self.height = height_dots
        self._image = Image.new(
            "L", (width_dots * SUPERSAMPLE, height_dots * SUPERSAMPLE), WHITE
        )
        self._draw = ImageDraw.Draw(self._image)

    # Mise à l'échelle

    def _s(self, value: float) -> float:
        return value * SUPERSAMPLE

    def _box(self, x0: float, y0: float, x1: float, y1: float):
        return [self._s(x0), self._s(y0), self._s(x1), self._s(y1)]

    def _stroke(self, width: int) -> int:
        return max(MIN_STROKE, width) * SUPERSAMPLE

    # Primitives

    def line(self, x0: float, y0: float, x1: float, y1: float, width: int = MIN_STROKE) -> None:
        self._draw.line(self._box(x0, y0, x1, y1), fill=BLACK, width=self._stroke(width))

    def rectangle(self, x0: float, y0: float, x1: float, y1: float,
                  width: int = MIN_STROKE, fill: bool = False) -> None:
        self._draw.rectangle(
            self._box(x0, y0, x1, y1),
            outline=BLACK,
            width=self._stroke(width),
            fill=BLACK if fill else None,
        )

    def ellipse(self, cx: float, cy: float, radius: float,
                width: int = MIN_STROKE, fill: bool = False) -> None:
        self._draw.ellipse(
            self._box(cx - radius, cy - radius, cx + radius, cy + radius),
            outline=BLACK,
            width=self._stroke(width),
            fill=BLACK if fill else None,
        )

    def polygon(self, points, width: int = MIN_STROKE, close: bool = True) -> None:
        scaled = [(self._s(x), self._s(y)) for x, y in points]
        if close:
            scaled.append(scaled[0])
        self._draw.line(scaled, fill=BLACK, width=self._stroke(width), joint="curve")

    def text(self, x: float, y: float, value: str, size_dots: int,
             anchor: str = "la") -> None:
        self._draw.text(
            (self._s(x), self._s(y)),
            value,
            font=load_font(size_dots),
            fill=BLACK,
            anchor=anchor,
        )

    def text_width(self, value: str, size_dots: int) -> float:
        """Largeur du texte en points finaux, pour centrer ou couper une ligne."""
        return self._draw.textlength(value, font=load_font(size_dots)) / SUPERSAMPLE

    def centered_text(self, y: float, value: str, size_dots: int) -> None:
        self.text(self.width / 2, y, value, size_dots, anchor="ma")

    # Sortie

    def to_bilevel(self) -> Image.Image:
        """Réduit à la taille finale puis seuille, sans tramage."""
        reduced = self._image.resize((self.width, self.height), Image.LANCZOS)
        return reduced.point(lambda v: 0 if v < THRESHOLD else 255, mode="1")

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_bilevel().save(path)
        return path

    def ink_ratio(self) -> float:
        """Part de points noirs. Un ticket très encré est lent et use la tête."""
        image = self.to_bilevel()
        black = sum(1 for pixel in image.getdata() if pixel == 0)
        return black / (self.width * self.height)
