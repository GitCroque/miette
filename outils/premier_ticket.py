"""Premier ticket de Miette (LET-103), à lancer depuis dolores.

Texte en mode ESC/POS avec les polices de la machine (règles de colonnes en
Font A et Font B, accents), puis la mire de `mire.py` en raster, puis le test
de largeur à 576 points, envoyé en GS v 0 brut pour contourner les contrôles
de largeur de python-escpos, et enfin une coupe.

    python3 outils/premier_ticket.py <adresse de l'imprimante> out/
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from escpos.printer import Network
from PIL import Image, ImageOps

# Les dizaines sont notées par une lettre : A pour 10, B pour 20, etc. Le
# dernier caractère de la première ligne donne le nombre de colonnes, par
# exemple « D12 » pour 42.
RULER = "".join(
    "ABCDEFG"[i // 10 - 1] if i % 10 == 0 else str(i % 10) for i in range(1, 71)
)


def raster(image: Image.Image) -> bytes:
    """GS v 0 d'une image 1 bit, sans passer par python-escpos."""
    ink = ImageOps.invert(image.convert("L")).convert("1")
    row = (ink.width + 7) // 8
    header = b"\x1dv0\x00" + bytes(
        [row & 0xFF, row >> 8, ink.height & 0xFF, ink.height >> 8]
    )
    return header + ink.tobytes()


def main(host: str, images: Path) -> None:
    p = Network(host, profile="TM-T88V")

    p.set(align="center", bold=True, double_width=True, double_height=True)
    p.text("MIETTE\n")
    p.set_with_default(align="center")
    p.text(f"Premier ticket, {date.today():%d/%m/%Y}\n\n")

    p.set_with_default()
    p.text("Colonnes en Font A :\n")
    p.text(RULER + "\n\n")
    p.set_with_default(font="b")
    p.text("Colonnes en Font B :\n")
    p.text(RULER + "\n\n")
    p.set_with_default()
    p.text("Accents : é è ê à ç ù ô œ É À €\n\n")

    p.image(str(images / "mire.png"), impl="bitImageRaster", center=False)
    p.text("\nLargeur : cette règle fait 576 points\n")
    p._raw(raster(Image.open(images / "regle-576.png")))
    p.text("\n")
    p.cut()
    p.close()


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
