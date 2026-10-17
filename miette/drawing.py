"""Dessins au trait écrits par Claude en SVG : coloriage, imagier, illustration.

Essai du 2026-10-17 avec Opus 5.5 en effort moyen : un sujet seul (chat,
voiture, maison) sort net et reconnaissable pour 1,4 à 2,7 centimes, en 7 à
15 secondes ; une scène à plusieurs personnages se brouille. L'illustration
d'une histoire demande donc un seul élément central, pas la scène entière.

Le SVG n'est jamais servi au navigateur : il est rendu en image 1 bit côté
serveur, l'aperçu montre donc exactement ce qui sortira sur le papier. Il est
aussi nettoyé avant le rendu : seules les formes passent, rien qui charge un
fichier ou exécute quoi que ce soit.
"""

from __future__ import annotations

import io
import random
import re
import xml.etree.ElementTree as ET

import anthropic
import resvg_py
from PIL import Image

from . import claude

# Un peu plus haut que pour le texte : épaissit légèrement le trait anticrénelé.
THRESHOLD = 160
# Au-delà, le modèle a rempli de noir des zones entières : lent à imprimer,
# fatigant pour la tête, et plus rien à colorier.
MAX_INK = 0.22
MIN_INK = 0.01

SYSTEM = """Tu dessines pour une imprimante thermique de ticket de caisse, noir et blanc pur, pour des enfants de 2 ans.
Réponds uniquement par un document SVG complet, sans aucun texte autour et sans balise de code.
Contraintes techniques : viewBox="0 0 512 512", aucun élément <text>, aucune image externe, aucun dégradé.
Uniquement des traits noirs (stroke="#000") ; remplissage "none" ou "#fff", jamais de noir plein sauf les pupilles.
Épaisseur de trait entre 10 et 14, stroke-linecap="round", stroke-linejoin="round".
Style : un dessin au trait de livre pour tout-petits. Formes simples et rondes, peu de détails,
de grandes zones fermées, pas de hachures ni d'ombres. Le sujet est grand, centré, et reconnaissable
au premier coup d'œil par un enfant de 2 ans. Un visage doux et souriant si le sujet en a un."""

# Le monde d'un enfant de 2 ans, avec l'article que l'imagier imprime.
SUBJECTS = (
    "le chat", "le chien", "le lapin", "le canard", "la vache", "le cochon", "le mouton",
    "le cheval", "la poule", "l'éléphant", "la girafe", "le lion", "l'ours", "le poisson",
    "l'escargot", "le papillon", "la coccinelle", "la tortue", "le hibou", "la souris",
    "la grenouille", "la baleine", "la voiture", "le camion", "le bus", "le tracteur",
    "le train", "le bateau", "l'avion", "le vélo", "la maison", "l'arbre", "la fleur",
    "le soleil", "la lune", "le nuage", "la pomme", "la banane", "la fraise", "le ballon",
    "le gâteau", "la chaussure", "le parapluie", "la tasse",
)

ALLOWED = {"svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon",
           "defs", "use", "style", "title", "desc"}
SVG_NS = "http://www.w3.org/2000/svg"


class DrawingError(claude.ClaudeError):
    """Dessin inutilisable : absent, illisible, vide ou trop noir."""


def noun(subject: str) -> str:
    """« l'éléphant » devient « éléphant », pour la consigne au modèle."""
    return re.sub(r"^(le |la |les |l')", "", subject)


def pick_subject(recent: list[str], rng: random.Random | None = None) -> str:
    rng = rng or random.Random()
    fresh = [s for s in SUBJECTS if s not in recent]
    return rng.choice(fresh or SUBJECTS)


def coloring_prompt(subject: str) -> str:
    return f"Coloriage : {noun(subject)}. De grandes zones fermées, faciles à colorier avec un gros crayon."


def picture_prompt(subject: str) -> str:
    return (f"Imagier : {noun(subject)}, seul, dans sa pose la plus typique, "
            "pour qu'un enfant de 2 ans le reconnaisse et le nomme.")


def illustration_prompt(title: str, paragraphs: tuple[str, ...] | list[str]) -> str:
    return (f"Illustration de l'histoire « {title} » ci-dessous. Dessine un seul élément central "
            "de l'histoire (le personnage principal, l'animal ou l'objet qui compte le plus), "
            "seul ou avec un seul autre élément, en grand. Pas de scène chargée ni de décor.\n\n"
            + "\n\n".join(paragraphs))


def build_request(prompt: str, model: str) -> dict:
    return {
        "model": model,
        "max_tokens": 8000,
        # L'effort moyen a donné les dessins jugés bons à l'essai ; le bas n'a pas été mesuré.
        "output_config": {"effort": "medium"},
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }


def sanitize(raw: str) -> str:
    """Extrait le SVG de la réponse et n'en garde que les formes."""
    found = re.search(r"<svg\b.*?</svg>", raw, re.S)
    if not found or re.search(r"<!(DOCTYPE|ENTITY)", raw):
        raise DrawingError("Le dessin reçu est illisible.")
    ET.register_namespace("", SVG_NS)
    try:
        root = ET.fromstring(found.group(0))
    except ET.ParseError as exc:
        raise DrawingError("Le dessin reçu est illisible.") from exc
    if _tag(root) != "svg" or "viewBox" not in root.attrib:
        raise DrawingError("Le dessin reçu est illisible.")
    _prune(root)
    return ET.tostring(root, encoding="unicode")


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _prune(element: ET.Element) -> None:
    for child in list(element):
        if _tag(child) not in ALLOWED:
            element.remove(child)
        else:
            _prune(child)
    for name, value in list(element.attrib.items()):
        # Un href ne doit viser qu'une forme du même dessin (<use href="#id">).
        if name.rsplit("}", 1)[-1] == "href" and not value.startswith("#"):
            del element.attrib[name]
        elif name.startswith("on"):
            del element.attrib[name]


def render(svg: str, width: int) -> Image.Image:
    """Rend le dessin en 1 bit à la largeur demandée, proportions gardées."""
    png = resvg_py.svg_to_bytes(svg_string=svg, width=width, background="white",
                                skip_system_fonts=True)
    image = Image.open(io.BytesIO(bytes(png))).convert("L")
    return image.point(lambda v: 0 if v < THRESHOLD else 255, mode="1")


def ink(image: Image.Image) -> float:
    return image.convert("L").histogram()[0] / (image.width * image.height)


def draw(prompt: str, *, key: str, model: str,
         client: anthropic.Anthropic | None = None) -> str:
    """Demande un dessin et le redemande une fois s'il est inutilisable."""
    payload = build_request(prompt, model)
    owned = client is None
    client = client or claude.client(key)
    try:
        error = None
        for _ in range(2):
            try:
                svg = sanitize(claude.complete(payload, client))
                share = ink(render(svg, 256))
                if share > MAX_INK:
                    raise DrawingError("Le dessin reçu est trop noir pour le ticket.")
                if share < MIN_INK:
                    raise DrawingError("Le dessin reçu est vide.")
                return svg
            except DrawingError as exc:
                error = exc
        raise DrawingError(f"{error} Réessayer dans un instant.")
    finally:
        if owned:
            client.close()
