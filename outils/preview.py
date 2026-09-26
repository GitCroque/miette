#!/usr/bin/env python3
"""Produit tous les tickets en PNG et contrôle ce qui peut l'être sans papier.

Tant que l'imprimante n'est pas là, c'est l'écran qui sert de juge. Chaque
image fait exactement la largeur du ticket, 576 points, donc ce qu'on voit
ici est ce qui sortira, à la binarisation près qui est déjà appliquée.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from miette.canvas import DOTS_PER_MM
from miette.generators import dot_to_dot, find_them, maze

OUT = Path(__file__).resolve().parent.parent / "out"


def line(label: str, sheet, extra: str = "") -> None:
    mm = round(sheet.height / DOTS_PER_MM)
    ink = round(sheet.ink_ratio() * 100, 1)
    print(f"  {label:34s} {mm:4d} mm   encre {ink:4.1f} %   {extra}")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    failures = []
    produced: list[Path] = []

    print("\nLabyrinthes")
    for level in maze.LEVELS:
        sheet = maze.render(level, seed=7)
        produced.append(sheet.save(OUT / f"maze-{level}.png"))
        cols, rows = maze.LEVELS[level]
        line(f"maze-{level}", sheet, f"{cols}x{rows}")

    print("\nPoints à relier")
    for shape in dot_to_dot.SHAPES:
        clashes = dot_to_dot.overlapping_labels(shape)
        if clashes:
            failures.append(f"numéros qui se chevauchent sur « {shape} » : {clashes}")
        sheet = dot_to_dot.render(shape)
        produced.append(sheet.save(OUT / f"dots-{shape}.png"))
        dot_to_dot.render(shape, show_outline=True).save(OUT / f"dots-{shape}-controle.png")
        count = len(dot_to_dot.SHAPES[shape])
        line(f"dots-{shape}", sheet, f"{count} points" + ("" if not clashes else "  ÉCHEC"))

    print("\nCherche et trouve")
    for target, occurrences in (("étoile", 3), ("poisson", 3), ("cœur", 4)):
        sheet, slots = find_them.render(target, occurrences=occurrences, seed=11)
        produced.append(sheet.save(OUT / f"find-{target}.png"))
        if len(slots) != occurrences:
            failures.append(f"« {target} » : {len(slots)} cibles posées pour {occurrences} demandées")
        line(f"find-{target}", sheet, f"cases {slots}")

    prune(produced)
    contact_sheet(produced)

    if failures:
        print("\nÉchecs :")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("\nTous les contrôles automatiques passent.")
    print("Reste à juger sur papier : lisibilité réelle du trait et des numéros.")
    return 0


def prune(produced: list[Path]) -> None:
    """Supprime les PNG laissés par une version précédente des générateurs.

    Sans ça, une forme retirée du jeu continue d'apparaître sur la planche et
    on croit avoir généré ce qui n'existe plus. Constaté avec une forme
    « bateau » abandonnée qui survivait dans out/.
    """
    keep = {path.name for path in produced}
    keep |= {f"dots-{shape}-controle.png" for shape in dot_to_dot.SHAPES}
    for path in OUT.glob("*.png"):
        if path.name.startswith("_") or path.name in keep:
            continue
        path.unlink()
        print(f"  orphelin supprimé : {path.name}")


def contact_sheet(paths: list[Path]) -> None:
    """Assemble une planche des tickets produits, pour un coup d'œil global."""
    if not paths:
        return
    images = [Image.open(p).convert("L") for p in paths]
    scale = 0.30
    width = int(images[0].width * scale)
    height = max(int(i.height * scale) for i in images)
    board = Image.new("L", (width * len(images), height), 255)
    for index, image in enumerate(images):
        board.paste(image.resize((width, int(image.height * scale)), Image.LANCZOS),
                    (index * width, 0))
    board.save(OUT / "_planche.png")
    print(f"\nPlanche : {OUT / '_planche.png'} ({len(images)} tickets)")


if __name__ == "__main__":
    sys.exit(main())
