# Miette

Une imprimante thermique de caisse posée dans la maison, et une page web sur le
téléphone : un appui, et une petite histoire du quotidien sort du rouleau,
écrite pour un tout-petit à partir de 2 ans. La machine ne produit pas des
documents, elle sème des miettes de papier qu'un enfant ramasse et garde.

## Ce que fait l'app

- Une page unique qui s'adapte à la largeur : barre d'onglets sur téléphone,
  navigation en haut sur iPad, barre latérale sur ordinateur. L'accueil propose
  une carte Surprise par enfant et une pour tous ensemble, les occasions
  (anniversaire, fêtes, voyage et visites, premières fois), la dernière
  histoire et les favoris. On lit l'aperçu, puis on imprime ou on en demande
  une autre.
- Un historique des histoires imprimées : relire, réimprimer, mettre en
  favori, supprimer. Sur ordinateur, la liste et la lecture côte à côte.
- Une fiche par enfant dans les réglages : prénom, mois de naissance, doudou,
  animaux de la maison, crèche, nounou, copains. L'âge calculé règle la
  longueur et le vocabulaire, les détails se glissent dans les histoires.
- L'histoire est écrite par un modèle Claude via l'[API Anthropic](https://platform.claude.com) :
  une situation du quotidien et au plus une petite émotion, dans l'esprit des
  livres pour tout-petits, puis composée en image avec Pillow et envoyée à
  l'imprimante en ESC/POS sur TCP 9100.
- L'état de l'imprimante (papier, capot, massicot) est lu avant d'imprimer.
- Fiches et histoires vivent dans une base SQLite sur le volume (`miette.db`) :
  une histoire se réimprime sans nouvel appel au modèle, et les titres récents
  sont écartés pour éviter les redites.
- Un champ libre accepte une demande en clair (« un coloriage de poule », « une
  histoire sur la tétine pour Noa ») : Claude la range d'abord en histoire à
  thème ou en coloriage d'un sujet précis, puis le déroulé habituel reprend.
- Chaque histoire reçoit une illustration, dessinée après le texte pendant
  qu'on lit l'aperçu, puis imprimée au-dessus du titre.
- Des dessins et des jeux, chacun sur son propre ticket : coloriage et imagier
  (un sujet du quotidien tiré au sort, avec son nom en grand pour l'imagier),
  labyrinthe en quatre niveaux, points à relier, cherche et trouve. L'aperçu
  montre le ticket exact, rendu par le serveur en noir et blanc.
- Un plafond quotidien d'histoires et de coloriages peut être posé contre un
  bouton qui s'emballe (`MIETTE_LIMITE_JOUR`) ; il n'y en a pas par défaut. Les
  jeux, calculés sur place, n'y comptent jamais.

## Matériel

Développé et mesuré sur une **Epson TM-T88VI** (rouleau de 80 mm, Ethernet) :
512 points utiles, 180 dpi dans les deux sens, 42 colonnes en Font A. Une image
plus large que 512 points est tronquée sans avertissement : les valeurs sont
dans `miette/ticket.py`, à adapter pour une autre machine. `python-escpos` n'a
pas de profil TM-T88VI, celui de la TM-T88V a les mêmes caractéristiques.
La machine n'accepte qu'une connexion à la fois sur le port 9100 : l'app
sérialise tous ses accès et garde l'état affiché quelques secondes en cache.

## Configuration

| Variable | Rôle | Défaut |
|---|---|---|
| `MIETTE_IMPRIMANTE` | Adresse de l'imprimante sur le réseau local | aucun, obligatoire |
| `MIETTE_IMPRIMANTE_PORT` | Port ESC/POS brut | `9100` |
| `ANTHROPIC_API_KEY` | Clé de l'API Anthropic | aucun, obligatoire |
| `MIETTE_MODELE` | Modèle Claude | `claude-opus-5-5` |
| `MIETTE_LIMITE_JOUR` | Plafond quotidien d'histoires et de coloriages | aucun : pas de plafond |
| `MIETTE_DONNEES` | Dossier de la base (fiches et histoires) | `/data` dans l'image |

Les dessins sont écrits par le même modèle, en SVG (effort moyen), puis
nettoyés (seules les formes passent) et rendus en 1 bit avec resvg. À l'essai,
un sujet seul sort net pour 1,5 à 3 centimes ; une scène à plusieurs
personnages se brouille, d'où une illustration centrée sur un seul élément de
l'histoire.

Haiku 4.5 a été écarté au premier essai : il laissait environ une faute de
français par histoire (accords, « calm » pour « calme »). Opus 5.5 tourne en
effort bas : sa réflexion ne se coupe pas, et une histoire de 150 mots n'en
demande pas davantage. Un refus des filtres de sécurité est rejoué côté
Anthropic sur le modèle de repli recommandé (`fallbacks: "default"`).

## Lancer

```bash
docker run -d -p 8090:8090 -v miette-data:/data \
  -e MIETTE_IMPRIMANTE=192.168.1.50 -e ANTHROPIC_API_KEY=... \
  ghcr.io/gitcroque/miette:latest
```

Puis ouvrir `http://<hôte>:8090` sur le téléphone, créer les fiches dans les
réglages, et ajouter la page à l'écran d'accueil. L'app n'a pas
d'authentification : sur Internet, la mettre derrière un proxy qui en fournit
une (Cloudflare Access, par exemple).

## Développer

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
MIETTE_IMPRIMANTE=... ANTHROPIC_API_KEY=... .venv/bin/uvicorn miette.app:app --reload --port 8090
```

Le dossier `outils/` contient les scripts d'atelier : `mire.py` et
`premier_ticket.py` (mire de référence de l'imprimante), `preview.py` (tous
les jeux en PNG avec leurs contrôles, pour les juger sans papier),
`icones.py` (icônes de l'app web).

## Licence

Code sous licence MIT. Polices Fredoka et Gelasio sous SIL Open Font License,
voir `miette/fonts/`.
