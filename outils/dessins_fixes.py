"""Dessins fixes des jeux, tirés une fois de MAI Image 2.6 et rangés dans le dépôt.

Le labyrinthe (un personnage et son but) et le cherche et trouve (les symboles)
ne demandent rien à OpenRouter quand l'enfant joue : leurs dessins sont tirés
ici, une fois, puis gardés en PNG 1 bit dans `miette/dessins/`.

Deux temps, pour ne payer les images qu'une fois et régler la mise au trait
autant qu'on veut :

    python outils/dessins_fixes.py --brut DOSSIER [--seulement cle,cle]
        demande les images (OPENROUTER_API_KEY), les garde telles quelles ;
    python outils/dessins_fixes.py --depuis DOSSIER [--seulement cle,cle]
        les met au trait à la taille du ticket et écrit miette/dessins/.

Le premier temps n'a besoin que de `miette.images` et de la clé : il tourne
aussi dans le conteneur de production, qui a déjà les deux.
"""

from __future__ import annotations

import argparse
import io
import math
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MODEL = "microsoft/mai-image-2.6"
OUT = Path(__file__).resolve().parent.parent / "miette" / "dessins"

PROMPT = (
    "Black and white line art for a toddler's game: {what}. Cute and friendly, alone, "
    "centered and filling the frame. It will be printed very small, about 2 cm, on a thermal "
    "receipt printer: extra thick bold black outlines, very few interior details, large simple "
    "shapes. Pure white background. No shading, no gray, no hatching, no texture, no filled "
    "black areas except small eyes, no text, no border, no ground, no background scenery."
)

# Dossier, taille maximale en points imprimante, et ce qu'il faut dessiner.
# Les clés sont les noms de fichiers lus par maze.py et find_them.py.
DRAWINGS = {
    "labyrinthe": (130, {
        "herisson": "a hedgehog walking, facing right",
        "lapin": "a bunny rabbit sitting, facing right",
        "souris": "a little mouse, facing right",
        "abeille": "a bee flying, facing right",
        "chien": "a puppy sitting, facing right",
        "ecureuil": "a squirrel with a big bushy tail, facing right",
        "ours": "a bear cub standing, facing right",
        "singe": "a little monkey, facing right",
        "chat": "a kitten sitting, facing right",
        "poussin": "a baby chick, facing right",
        "escargot": "a snail, facing right",
        "pomme": "an apple with one leaf, no face",
        "carotte": "a carrot with its leaves, no face",
        "fromage": "a triangular wedge of Swiss cheese seen from the side, with round holes, no face",
        "fleur": "a flower with round petals and a stem, no face",
        "os": "a dog bone, no face",
        "pin": "a pine cone, no face",
        "miel": "a honey pot, no face",
        "banane": "a banana, no face",
        "pelote": "a ball of yarn, no face",
        "poule": "a mother hen sitting, facing left",
        "salade": "a head of lettuce, no face",
    }),
    "cherche": (86, {
        "etoile": "a five-pointed star, no face",
        "maison": "a small house with a pointed roof, a door and one window, no face",
        "coeur": "a heart, no face",
        "poisson": "a fish seen from the side, with one round eye and a forked tail",
        "sapin": "a fir tree with a short trunk, no decorations, no face",
        "champignon": "a mushroom with a round cap with a few spots and a short stem, no face",
    }),
}

# Trait minimal sur le ticket : en dessous, la tête thermique le rend gris et
# haché (même seuil que les jeux, voir canvas.MIN_STROKE).
MIN_STROKE = 3


def _wanted(only: str | None):
    keys = set(only.split(",")) if only else None
    for folder, (size, items) in DRAWINGS.items():
        for key, what in items.items():
            if keys is None or key in keys:
                yield folder, size, key, what


def fetch_all(directory: Path, only: str | None) -> int:
    import os

    from miette import images

    key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("MIETTE_MODELE_COLORIAGE", MODEL)
    jobs = list(_wanted(only))

    def one(job):
        folder, _, name, what = job
        target = directory / folder / f"{name}.img"
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_bytes(images.fetch(PROMPT.format(what=what), key=key, model=model))
            return f"{folder}/{name} : reçu"
        except images.ImageError as exc:
            return f"{folder}/{name} : ÉCHEC {exc}"

    failures = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for line in pool.map(one, jobs):
            failures += "ÉCHEC" in line
            print(line, flush=True)
    return 1 if failures else 0


def stroke(bits) -> float:
    """Épaisseur médiane des segments noirs, à l'horizontale et à la verticale."""
    width, height = bits.size
    pixels = bits.load()
    runs = []
    for outer, inner, get in ((height, width, lambda a, b: pixels[b, a]),
                              (width, height, lambda a, b: pixels[a, b])):
        for a in range(outer):
            run = 0
            for b in range(inner):
                if get(a, b) == 0:
                    run += 1
                elif run:
                    runs.append(run)
                    run = 0
            if run:
                runs.append(run)
    return statistics.median(runs) if runs else 0.0


def line_art(raw: bytes, size: int):
    """Met une image reçue au trait, dans un carré de `size` points, trait d'au moins 3 points."""
    from PIL import Image, ImageFilter, ImageOps

    from miette import drawing

    image = Image.open(io.BytesIO(raw))
    image.load()
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flat = Image.new("RGBA", image.size, "white")
        flat.alpha_composite(image)
        image = flat
    gray = image.convert("L")

    def bits_of(picture):
        return picture.point(lambda v: 0 if v < drawing.THRESHOLD else 255, mode="1")

    box = ImageOps.invert(bits_of(gray).convert("L")).getbbox()
    if box is None:
        raise ValueError("image vide")
    gray = gray.crop(box)
    scale = size / max(gray.size)
    # Épaissir avant de réduire : le trait reçu, ramené à 2 cm, tomberait à un
    # ou deux points.
    needed = (MIN_STROKE + 0.5) / scale
    current = stroke(bits_of(gray))
    if current < needed:
        grow = math.ceil((needed - current) / 2)
        gray = ImageOps.expand(gray, border=grow, fill=255).filter(ImageFilter.MinFilter(2 * grow + 1))
        scale = size / max(gray.size)
    small = gray.resize((max(1, round(gray.width * scale)), max(1, round(gray.height * scale))),
                        Image.LANCZOS)
    bits = bits_of(small)
    return bits.crop(ImageOps.invert(bits.convert("L")).getbbox())


def process_all(directory: Path, only: str | None) -> int:
    from miette import drawing

    missing = 0
    for folder, size, name, _ in _wanted(only):
        source = directory / folder / f"{name}.img"
        if not source.exists():
            print(f"{folder}/{name} : pas d'image brute")
            missing += 1
            continue
        bits = line_art(source.read_bytes(), size)
        target = OUT / folder / f"{name}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        bits.save(target, optimize=True)
        print(f"{folder}/{name} : {bits.width}x{bits.height}, trait {stroke(bits):.1f}, "
              f"encre {drawing.ink(bits):.0%}")
    return 1 if missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--brut", type=Path, help="demande les images et les range ici")
    group.add_argument("--depuis", type=Path, help="met au trait les images rangées ici")
    parser.add_argument("--seulement", help="clés à traiter, séparées par des virgules")
    args = parser.parse_args()
    if args.brut:
        return fetch_all(args.brut, args.seulement)
    return process_all(args.depuis, args.seulement)


if __name__ == "__main__":
    sys.exit(main())
