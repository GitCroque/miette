"""Coloriages et illustrations dessinés par un modèle d'image, via l'API Images d'OpenRouter.

Comparatif du 2026-11-01 (chat, camion de pompiers, girafe, rendus en 1 bit
comme sur le ticket) : les modèles d'image battent nettement les SVG écrits
par Claude, avec de vrais visages et de vraies proportions. Julien a retenu
MAI Image 2.6 de Microsoft : environ 3,9 centimes et 25 secondes par image,
et un trait de 4 à 9 points à la largeur du ticket, assez épais pour la tête
thermique sans retouche.

Le compte OpenRouter n'accepte que les fournisseurs compatibles ZDR (aucune
donnée gardée) : MAI y passe par Azure. Recraft, FLUX et les modèles d'image
d'OpenAI n'en ont aucun.

Le dessin est mis au trait dès réception, puis gardé tel quel dans la base :
l'aperçu, l'impression et la réimpression montrent le même ticket.

Une illustration part d'une description écrite par Claude, sans aucun nom
(voir drawing.scene) : l'histoire elle-même ne quitte jamais Anthropic.
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
import urllib.request

from PIL import Image, UnidentifiedImageError

from . import drawing

URL = "https://openrouter.ai/api/v1/images"
# Le tunnel Cloudflare coupe une requête à 100 secondes : un appel bloqué doit
# laisser le temps au repli sur Claude.
TIMEOUT = 60

PROMPT = (
    "Coloring page for a 2-year-old child: a single {subject} (French word), cute and friendly, "
    "alone, in its most typical pose so that a 2-year-old recognizes it and says its name. "
    "Centered and filling the frame. Very thick bold black outlines only, on a pure white background. "
    "No shading, no gray, no hatching, no texture, no filled black areas, no text, no border, "
    "no background scenery. Large simple closed shapes that are easy to color with a big crayon. "
    "Children's coloring book style."
)


ILLUSTRATION = (
    "Black and white illustration for a picture book for 2-year-olds: {scene}. "
    "Cute and friendly, one or two characters at most, large, centered and filling the frame. "
    "Very thick bold black outlines only, on a pure white background. "
    "No shading, no gray, no hatching, no texture, no filled black areas, no text, no letters, "
    "no border, no background scenery. Large simple closed shapes, children's coloring book style."
)


class ImageError(Exception):
    """Dessin impossible à obtenir d'OpenRouter : l'app se replie sur Claude."""


class UnusableImage(ImageError):
    """Une image est arrivée, mais elle ne fait pas un coloriage."""


def coloring_prompt(subject: str) -> str:
    return PROMPT.format(subject=drawing.noun(subject))


def illustration_prompt(scene: str) -> str:
    return ILLUSTRATION.format(scene=scene)


def build_request(prompt: str, model: str) -> dict:
    return {"model": model, "prompt": prompt, "aspect_ratio": "1:1"}


def _post(body: dict, key: str) -> dict:
    request = urllib.request.Request(
        URL, data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.load(response)


def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode(errors="replace").lower()
    except (OSError, AttributeError):
        return ""


def fetch(prompt: str, *, key: str, model: str) -> bytes:
    """Demande une image et rend ses octets, tels qu'envoyés par le modèle."""
    if not key:
        raise ImageError("Aucune clé OpenRouter : renseigner OPENROUTER_API_KEY.")
    try:
        answer = _post(build_request(prompt, model), key)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise ImageError("Clé OpenRouter refusée (OPENROUTER_API_KEY) : à renouveler.") from exc
        if exc.code == 402:
            raise ImageError("Crédit OpenRouter épuisé.") from exc
        if exc.code == 404:
            raise ImageError(f"{model} indisponible avec les règles du compte OpenRouter.") from exc
        if exc.code == 400 and "moderation" in _error_text(exc):
            # Constaté le 2026-11-01 sur « une petite fille qui rit dans son bain ».
            raise ImageError("Dessin refusé par la modération du fournisseur.") from exc
        raise ImageError(f"OpenRouter a répondu {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ImageError(f"OpenRouter injoignable : {type(exc).__name__}.") from exc
    except ValueError as exc:
        raise ImageError("Réponse d'OpenRouter illisible.") from exc
    try:
        return base64.b64decode(answer["data"][0]["b64_json"])
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise UnusableImage("OpenRouter n'a rendu aucune image.") from exc


def line_art(raw: bytes, width: int) -> Image.Image:
    """Met l'image au trait : fond blanc, largeur du ticket, seuil, 1 bit, sans marge vide."""
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise UnusableImage("L'image reçue est illisible.") from exc
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        flat = Image.new("RGBA", image.size, "white")
        flat.alpha_composite(image)
        image = flat
    gray = image.convert("L")
    gray = gray.resize((width, round(gray.height * width / gray.width)), Image.LANCZOS)
    bits = gray.point(lambda v: 0 if v < drawing.THRESHOLD else 255, mode="1")
    share = drawing.ink(bits)
    if share > drawing.MAX_INK:
        raise UnusableImage("Le dessin reçu est trop noir pour le ticket.")
    if share < drawing.MIN_INK:
        raise UnusableImage("Le dessin reçu est vide.")
    return drawing.trim(bits)


def draw(prompt: str, *, key: str, model: str, width: int) -> Image.Image:
    """Le coloriage mis au trait, redemandé une fois si l'image est inutilisable.

    Une panne (clé, réseau, refus) n'est pas retentée : le repli sur Claude
    doit tenir avant la coupure du tunnel.
    """
    error: UnusableImage | None = None
    for _ in range(2):
        try:
            return line_art(fetch(prompt, key=key, model=model), width)
        except UnusableImage as exc:
            error = exc
    raise error


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
