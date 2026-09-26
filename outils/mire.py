"""Mire de référence de l'imprimante Miette (LET-103).

Produit deux images 1 bit dans `out/` :

- `mire.png`, 512 points de large : règle, épaisseurs de trait dans les deux
  sens, barres d'étalonnage de 360 points, aplat noir, dégradé tramé, cercles et
  texte composé en raster à plusieurs tailles ;
- `regle-576.png`, 576 points de large : sert à vérifier la largeur réellement
  imprimable. Si la graduation s'arrête à 512, la machine est bien à 512 points.

Tout est dessiné directement à la résolution finale, sans suréchantillonnage :
une mire doit montrer le point tel qu'il est, pas un trait lissé puis seuillé.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "out"
WIDTH = 512
WHITE, BLACK = 255, 0

SANS = "/System/Library/Fonts/Supplemental/Verdana.ttf"
SANS_BOLD = "/System/Library/Fonts/Supplemental/Verdana Bold.ttf"
SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"
ROUNDED = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def ruler(draw: ImageDraw.ImageDraw, y: int, width: int, label: ImageFont.FreeTypeFont) -> int:
    """Graduation tous les 8 points, repère tous les 32, étiquette tous les 64."""
    for x in range(0, width, 8):
        length = 24 if x % 64 == 0 else 14 if x % 32 == 0 else 7
        draw.rectangle([x, y, x + 1, y + length], fill=BLACK)
    draw.rectangle([width - 2, y, width - 1, y + 24], fill=BLACK)
    for x in range(64, width + 1, 64):
        text = str(x)
        w = draw.textlength(text, font=label)
        draw.text((min(x - w / 2, width - w - 4), y + 28), text, font=label, fill=BLACK)
    return y + 28 + label.size + 6


def build_mire() -> Image.Image:
    height = 1500
    img = Image.new("L", (WIDTH, height), WHITE)
    d = ImageDraw.Draw(img)
    small = font(SANS, 18)
    bold = font(SANS_BOLD, 22)

    # Cadre de 2 points : ses bords gauche et droit disent si les 512 points
    # sortent en entier.
    d.rectangle([0, 0, WIDTH - 1, height - 1], outline=BLACK, width=2)

    y = 12
    d.text((12, y), "MIRE MIETTE  TM-T88VI", font=bold, fill=BLACK)
    y += 36
    y = ruler(d, y, WIDTH, small)

    # Épaisseurs dans le sens de la tête (horizontal) et dans le sens de
    # l'avance du papier (vertical) : le thermique ne les rend pas pareil.
    y += 10
    d.text((12, y), "Traits horizontaux", font=bold, fill=BLACK)
    y += 34
    for thickness in (1, 2, 3, 4, 6):
        d.rectangle([12, y, 12 + 360 - 1, y + thickness - 1], fill=BLACK)
        d.text((390, y - 10), f"{thickness} pt", font=small, fill=BLACK)
        y += 30

    y += 10
    d.text((12, y), "Traits verticaux", font=bold, fill=BLACK)
    y += 34
    x = 24
    for thickness in (1, 2, 3, 4, 6):
        d.rectangle([x, y, x + thickness - 1, y + 90], fill=BLACK)
        d.text((x - 6, y + 98), f"{thickness}", font=small, fill=BLACK)
        x += 60
    y += 130

    # Étalonnage : 360 points font 50,8 mm à 180 dpi et 45,0 mm à 203 dpi.
    # À mesurer à la règle, dans les deux sens.
    d.text((12, y), "Barres de 360 points, à mesurer :", font=bold, fill=BLACK)
    y += 30
    d.text((12, y), "50,8 mm si 180 dpi, 45,0 mm si 203 dpi", font=small, fill=BLACK)
    y += 34
    d.rectangle([12, y, 12 + 360 - 1, y + 5], fill=BLACK)
    d.rectangle([12, y - 12, 13, y + 17], fill=BLACK)
    d.rectangle([12 + 358, y - 12, 12 + 359, y + 17], fill=BLACK)
    y += 30
    bar_top = y
    d.rectangle([440, bar_top, 445, bar_top + 360 - 1], fill=BLACK)
    d.rectangle([428, bar_top, 457, bar_top + 1], fill=BLACK)
    d.rectangle([428, bar_top + 358, 457, bar_top + 359], fill=BLACK)
    d.text((12, y), "Barre verticale à droite :", font=small, fill=BLACK)
    d.text((12, y + 24), "sens de l'avance papier", font=small, fill=BLACK)

    # Cercles : tenue des courbes à 3 et 4 points.
    d.ellipse([20, y + 70, 180, y + 230], outline=BLACK, width=3)
    d.ellipse([210, y + 70, 370, y + 230], outline=BLACK, width=4)
    d.text((80, y + 238), "3 pt", font=small, fill=BLACK)
    d.text((270, y + 238), "4 pt", font=small, fill=BLACK)
    y = bar_top + 360 + 20

    d.text((12, y), "Aplat noir", font=bold, fill=BLACK)
    y += 32
    d.rectangle([12, y, WIDTH - 13, y + 47], fill=BLACK)
    y += 64

    # Le tramage n'est pas retenu pour le trait, mais la mire doit montrer ce
    # qu'il donne sur ce papier, pour le jour où une photo passera.
    d.text((12, y), "Dégradé tramé (Floyd-Steinberg)", font=bold, fill=BLACK)
    y += 32
    gradient = Image.linear_gradient("L").rotate(90).resize((WIDTH - 24, 64))
    gradient = gradient.convert("1").convert("L")
    img.paste(gradient, (12, y))
    y += 84

    d.text((12, y), "Texte composé en image", font=bold, fill=BLACK)
    y += 36
    for size in (18, 22, 26, 32):
        d.text((12, y), f"Il était une fois ({size})", font=font(SERIF, size), fill=BLACK)
        y += size + 14
    y += 6
    d.text((12, y), "Miette", font=font(ROUNDED, 64), fill=BLACK)
    y += 90

    img = img.crop((0, 0, WIDTH, y + 10))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, WIDTH - 1, img.height - 1], outline=BLACK, width=2)
    return img.convert("1", dither=Image.Dither.NONE)


def build_width_test() -> Image.Image:
    width = 576
    img = Image.new("L", (width, 90), WHITE)
    d = ImageDraw.Draw(img)
    ruler(d, 6, width, font(SANS, 18))
    # Deux repères pleins, à 512 et à 576 : on voit lequel sort.
    d.rectangle([505, 60, 511, 89], fill=BLACK)
    d.rectangle([569, 60, 575, 89], fill=BLACK)
    return img.convert("1", dither=Image.Dither.NONE)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    mire = build_mire()
    mire.save(OUT / "mire.png")
    build_width_test().save(OUT / "regle-576.png")
    print(f"mire.png : {mire.width} x {mire.height} points")


if __name__ == "__main__":
    main()
