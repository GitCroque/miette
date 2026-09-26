# Miette

Une imprimante thermique de caisse posée dans la maison, et une page web sur le
téléphone : un appui, et une petite histoire sort du rouleau, écrite pour un
enfant de 3 à 5 ans qui en est le héros. La machine ne produit pas des
documents, elle sème des miettes de papier qu'un enfant ramasse et garde.

## Ce que fait l'app

- Une page unique, pensée pour l'écran d'accueil de l'iPhone : un prénom, un
  thème (ou une surprise), un bouton.
- L'histoire est écrite par un modèle Claude via [OpenRouter](https://openrouter.ai)
  (80 à 150 mots, une seule péripétie, une fin rassurante), puis composée en
  image avec Pillow et envoyée à l'imprimante en ESC/POS sur TCP 9100.
- L'état de l'imprimante (papier, capot, massicot) est lu avant d'écrire
  l'histoire : on ne paie pas un texte qui ne pourra pas sortir.
- Les histoires sont gardées dans un carnet (`histoires.jsonl`) et se
  réimpriment sans nouvel appel au modèle.
- Un plafond quotidien protège contre un bouton qui s'emballe.

## Matériel

Développé et mesuré sur une **Epson TM-T88VI** (rouleau de 80 mm, Ethernet) :
512 points utiles, 180 dpi dans les deux sens, 42 colonnes en Font A. Une image
plus large que 512 points est tronquée sans avertissement : les valeurs sont
dans `miette/ticket.py`, à adapter pour une autre machine. `python-escpos` n'a
pas de profil TM-T88VI, celui de la TM-T88V a les mêmes caractéristiques.

## Configuration

| Variable | Rôle | Défaut |
|---|---|---|
| `MIETTE_IMPRIMANTE` | Adresse de l'imprimante sur le réseau local | aucun, obligatoire |
| `MIETTE_IMPRIMANTE_PORT` | Port ESC/POS brut | `9100` |
| `OPENROUTER_API_KEY` | Clé OpenRouter | aucun, obligatoire |
| `MIETTE_MODELE` | Modèle OpenRouter | `anthropic/claude-sonnet-5` |
| `MIETTE_RENDU` | `raster` (page composée en image) ou `texte` (police de la machine) | `raster` |
| `MIETTE_LIMITE_JOUR` | Nombre maximal d'histoires générées par jour | `20` |
| `MIETTE_DONNEES` | Dossier du carnet d'histoires | `/data` dans l'image |

Sonnet 5 plutôt que Haiku 4.5 : sur un premier essai, Haiku laissait environ
une faute de français par histoire (accords, « calm » pour « calme »), Sonnet
aucune, pour environ 0,3 centime par histoire.

## Lancer

```bash
docker run -d -p 8090:8090 -v miette-data:/data \
  -e MIETTE_IMPRIMANTE=192.168.1.50 -e OPENROUTER_API_KEY=... \
  ghcr.io/gitcroque/miette:latest
```

Puis ouvrir `http://<hôte>:8090` sur le téléphone et l'ajouter à l'écran
d'accueil. L'app n'a pas d'authentification : elle est faite pour le réseau
de la maison, pas pour Internet.

## Développer

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
MIETTE_IMPRIMANTE=... OPENROUTER_API_KEY=... .venv/bin/uvicorn miette.app:app --reload --port 8090
```

Le dossier `outils/` contient les scripts d'atelier : `mire.py` et
`premier_ticket.py` (mire de référence de l'imprimante), `preview.py` (jeux
imprimables : labyrinthe, points à relier, cherche et trouve, pas encore
branchés sur l'app), `icones.py` (icônes de l'app web).

## Licence

Code sous licence MIT. Polices Fredoka et Gelasio sous SIL Open Font License,
voir `miette/fonts/`.
