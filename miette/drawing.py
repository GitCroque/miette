"""Dessins au trait écrits par Claude en SVG, en repli du modèle d'image.

Depuis le 2026-11-01, coloriages et illustrations viennent d'un modèle d'image
quand une clé OpenRouter est posée (voir images.py) ; Claude les dessine
encore sans elle, ou quand le modèle d'image échoue.

Pour une illustration, le modèle d'image ne reçoit jamais l'histoire : Claude
la lit et décrit le dessin en quelques mots d'anglais, sans aucun nom
(`scene`), et seuls ces mots partent chez OpenRouter. Un contrôle côté
serveur bloque l'envoi si un mot propre des fiches s'y glisse quand même.

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
import unicodedata
import xml.etree.ElementTree as ET

import anthropic
import resvg_py
from PIL import Image, ImageOps

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

# Le monde d'un enfant de 2 ans par thème, avec l'article imprimé sous le dessin.
# Le coloriage sert aussi d'imagier (fusion décidée par Julien le 2026-10-17) :
# on colorie le sujet et on dit son nom ensemble.
CATEGORIES = {
    "animaux": ("Animaux", (
        "le chat", "le chien", "le lapin", "le canard", "la vache", "le cochon", "le mouton",
        "le cheval", "la poule", "l'éléphant", "la girafe", "le lion", "l'ours", "le poisson",
        "l'escargot", "le papillon", "la coccinelle", "la tortue", "le hibou", "la souris",
        "la grenouille", "la baleine", "le singe", "le hérisson", "le pingouin", "le zèbre",
    )),
    "vehicules": ("Véhicules", (
        "la voiture", "le camion", "le bus", "le tracteur", "le train", "le bateau", "l'avion",
        "le vélo", "l'hélicoptère", "la fusée", "la moto", "le camion de pompiers",
        "la trottinette", "la montgolfière",
    )),
    "maison": ("À la maison", (
        "la maison", "la chaussure", "le parapluie", "la tasse", "le ballon", "le bonnet",
        "la brosse à dents", "la lampe", "le lit", "la chaise", "le seau et la pelle",
        "le cadeau", "la poussette",
    )),
    "nature": ("Nature", (
        "l'arbre", "la fleur", "le soleil", "la lune", "le nuage", "l'étoile", "le champignon",
        "l'arc-en-ciel", "la feuille", "le sapin", "la montagne", "le bonhomme de neige",
    )),
    "a-manger": ("À manger", (
        "la pomme", "la banane", "la fraise", "le gâteau", "la carotte", "la poire", "la glace",
        "le croissant", "les cerises", "la pastèque", "le biberon", "la tartine",
    )),
}
SUBJECTS = tuple(subject for _, subjects in CATEGORIES.values() for subject in subjects)

ALLOWED = {"svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon",
           "defs", "use", "style", "title", "desc"}
SVG_NS = "http://www.w3.org/2000/svg"


class DrawingError(claude.ClaudeError):
    """Dessin inutilisable : absent, illisible, vide ou trop noir."""


def noun(subject: str) -> str:
    """« l'éléphant » devient « éléphant », pour la consigne au modèle."""
    return re.sub(r"^(le |la |les |l')", "", subject)


def pick_subject(recent: list[str], category: str | None = None,
                 rng: random.Random | None = None) -> str:
    """Un sujet du thème demandé (de tous les thèmes pour une surprise), sans redite récente."""
    rng = rng or random.Random()
    subjects = CATEGORIES[category][1] if category else SUBJECTS
    fresh = [s for s in subjects if s not in recent]
    return rng.choice(fresh or subjects)


def coloring_prompt(subject: str) -> str:
    return (f"Coloriage : {noun(subject)}, seul, dans sa pose la plus typique, pour qu'un enfant "
            "de 2 ans le reconnaisse et le nomme. De grandes zones fermées, faciles à colorier "
            "avec un gros crayon.")


def illustration_prompt(title: str, paragraphs: tuple[str, ...] | list[str]) -> str:
    return (f"Illustration de l'histoire « {title} » ci-dessous. Dessine un seul élément central "
            "de l'histoire (le personnage principal, l'animal ou l'objet qui compte le plus), "
            "seul ou avec un seul autre élément, en grand. Pas de scène chargée ni de décor.\n\n"
            + "\n\n".join(paragraphs))


SCENE_SYSTEM = """Tu choisis le dessin qui illustrera une histoire pour tout-petit, imprimée en noir et blanc sur un ticket de caisse.
Un modèle d'image le dessinera d'après ta description, sans jamais voir l'histoire.
Réponds par une seule ligne en anglais, de 6 à 20 mots, sans rien autour : ce qu'il faut dessiner.
Un seul élément central de l'histoire (le personnage principal, l'animal ou l'objet qui compte le plus),
seul ou avec un seul autre élément, en train de faire quelque chose de simple. Pas de décor.
Aucun nom propre, jamais : ni prénom, ni nom de doudou, d'animal, de crèche ou de personne.
Décris plutôt : « a little girl », « a little boy », « a toddler », « a teddy rabbit », « a grey cat ».
Rien d'écrit à dessiner : ni mot, ni lettre, ni chiffre.
Jamais un enfant au bain, déshabillé, à la toilette ou au change : la modération du modèle d'image refuse
ces scènes. Dessine alors l'objet qui compte (le canard en plastique, la serviette, le pot)."""

# Champs des fiches qui peuvent porter un nom : prénom, doudou, animaux, crèche, nounou, copains.
PRIVATE_FIELDS = ("prenom", "doudou", "animaux", "creche", "nounou", "copains")
MAX_SCENE = 200


def _words(text: str) -> list[str]:
    """Mots sans accents ni ponctuation, pour comparer « Chloé » et « Chloe »."""
    plain = unicodedata.normalize("NFKD", text)
    plain = "".join(c for c in plain if not unicodedata.combining(c))
    return re.findall(r"[^\W\d_]+", plain)


def private_words(children: list[dict]) -> set[str]:
    """Les mots propres des fiches : les prénoms, et tout mot à majuscule des autres champs.

    Un doudou « Pinpin, un lapin gris » donne « pinpin » : le reste est un nom
    commun français, sans risque de se retrouver dans une description anglaise.
    """
    found = set()
    for child in children:
        found.update(w.lower() for w in _words(child.get("prenom", "")))
        for field in PRIVATE_FIELDS[1:]:
            found.update(w.lower() for w in _words(child.get(field, "")) if w[0].isupper())
    return {w for w in found if len(w) > 1}


def scene_request(title: str, paragraphs: tuple[str, ...] | list[str], model: str) -> dict:
    return {
        "model": model,
        # Quelques mots à écrire : la marge sert à la réflexion, qui ne se coupe pas.
        "max_tokens": 2000,
        "output_config": {"effort": "low"},
        "system": SCENE_SYSTEM,
        "messages": [{"role": "user", "content": f"« {title} »\n\n" + "\n\n".join(paragraphs)}],
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }


def scene(title: str, paragraphs: tuple[str, ...] | list[str], *, private: set[str],
          key: str, model: str, client: anthropic.Anthropic | None = None) -> str:
    """Ce qu'il faut dessiner pour illustrer l'histoire, en anglais et sans aucun nom des fiches."""
    owned = client is None
    client = client or claude.client(key)
    try:
        raw = claude.complete(scene_request(title, paragraphs, model), client)
    finally:
        if owned:
            client.close()
    lines = [line.strip().strip("\"'`«»“”").strip() for line in raw.splitlines()]
    description = next((line for line in lines if line), "").rstrip(".")
    if not description or len(description) > MAX_SCENE:
        raise DrawingError("Le sujet de l'illustration est illisible.")
    if private & {w.lower() for w in _words(description)}:
        raise DrawingError("Le sujet de l'illustration cite un nom des fiches : rien n'est envoyé.")
    return description


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


def trim(image: Image.Image, padding: int = 12) -> Image.Image:
    """Retire le blanc au-dessus et au-dessous du sujet, à quelques points près.

    Le modèle dessine dans un carré : un sujet large et bas (le bus, le
    train) laissait jusqu'à la moitié du carré vide, donc du papier perdu.
    """
    box = ImageOps.invert(image.convert("L")).getbbox()
    if box is None:
        return image
    return image.crop((0, max(0, box[1] - padding), image.width, min(image.height, box[3] + padding)))


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
