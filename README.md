# Le Sosie

Importez vos dépenses CSV et posez une question en français. Claude transforme la
question en requête structurée validée ; Python et SQL calculent indépendamment
sur SQLite. Le serveur compare les montants **et les dépenses utilisées**, puis
l'interface affiche la réponse, les preuves et les durées. Aucun montant final
n'est rédigé par le LLM.

## Démarrage rapide

Prérequis : Git, Docker avec Compose v2 et une clé API Anthropic disposant de
crédits et d'un accès au modèle configuré. Le lancement vise une démonstration locale.

```sh
git clone https://github.com/John-Natty/Holberton-school-Hackathon-le-Sosie.git
cd Holberton-school-Hackathon-le-Sosie
cp .env.example .env
```

Renseigner **`ANTHROPIC_API_KEY` dans `.env`**, puis :

```sh
docker compose up --build
```

Ouvrir **http://localhost:5000**. Arrêter avec `Ctrl+C`, puis `docker compose down`.
La construction nécessite Internet ; prévoir environ cinq minutes selon le réseau.
Le code de ce palier doit être présent dans la révision clonée.

## Démonstration

Enregistrer ce contenu dans un fichier `depenses.csv` :

```csv
date,description,categorie,montant
2026-09-01,Carrefour,Alimentation,42.50
2026-09-03,Boulangerie,Alimentation,12.00
2026-09-04,Restaurant,Alimentation,18.00
```

Importer ce fichier, puis demander : **« Combien ai-je dépensé en alimentation ? »**.
Sur une base neuve, les deux résultats doivent afficher **72,50 €**, les trois mêmes
identifiants et une concordance. Chaque import ajoute des dépenses : réimporter le
même fichier crée des doublons.

« Combien ai-je dépensé récemment ? » doit demander une période, sans calcul.
Une divergence ou l'échec d'un calculateur ne produit jamais de réponse validée.

Les CSV doivent être en UTF-8, séparés par des virgules, avec les quatre colonnes
ci-dessus. Un montant avec virgule doit être entre guillemets (`"42,50"`). Au plus
deux décimales ; montants négatifs refusés. Limite du fichier : 2 Mio. **Toute ligne
invalide fait refuser l'import entier**, sans enregistrement partiel.

## Configuration et stockage

| Variable | Rôle |
| --- | --- |
| `FLASK_APP=app.wsgi:app` | Point d'entrée Flask |
| `APP_PORT=5000` | Port local publié par Docker |
| `ANTHROPIC_API_KEY` | Seule valeur secrète à renseigner, côté serveur |
| `ANTHROPIC_MODEL=claude-sonnet-5` | Modèle Claude, configurable selon l'accès API |
| `DATABASE_PATH=data/data.db` | Base SQLite dans le volume Docker `/app/data` |

Compose transmet `.env` au conteneur. Si `APP_PORT` change, adapter l'URL.
Le volume `sqlite_data` conserve dépenses et calculs après un arrêt ou une
reconstruction. Il est initialisé avec les droits de l'utilisateur non root
`appuser`. Le dossier parent de la base est créé automatiquement. Une base ancienne
reçoit la colonne de durée manquante ; les anciens calculs affichent une durée
indisponible, sans valeur inventée. Pour garder une ancienne base `data.db` en local,
conserver son chemin dans `.env` ; aucune base existante n'est déplacée automatiquement.

Sans clé, la page, l'import et la consultation fonctionnent ; `/chat` affiche une
erreur de configuration explicite. Aucun mode de calcul simulé n'existe dans
l'application. Le [contrat HTTP](docs/API_FRONTEND.md) décrit les réponses.
Le SDK `anthropic==1.4.0` utilise
[`messages.create(output_config=...)`](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

## Lancement sans Docker

Prérequis : Python 3.12 ou supérieur. Après création et configuration de `.env` :

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
set -a
. ./.env
set +a
flask run --no-debugger --no-reload
```

## Tests

Prérequis supplémentaires : Node.js 18 ou supérieur, environnement Python ci-dessus.
Installer les dépendances de test et Chromium (Linux : `--with-deps` peut demander
les droits administrateur pour les bibliothèques système) :

```sh
. .venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install --with-deps chromium
python -m pytest -q
node --check static/js/app.js
node tests/frontend.test.cjs
docker compose --env-file .env.example config --quiet
```

`pytest` exécute les tests Python, dont les fixtures `tmp_path` et le parcours
Chromium → vrai Flask → SDK Anthropic → SQLite → Python/SQL → rendu JavaScript.
Seule la réponse HTTP externe de Claude est simulée dans les tests ; les tests de
divergence remplacent aussi explicitement un calculateur. Aucune clé ni dépense
réelle n'est utilisée. Les bases de test sont temporaires.

Le test final avec Claude réel reste le parcours Docker et CSV décrit plus haut,
avec une vraie clé. Il vérifie aussi l'accès au modèle, les crédits et l'interprétation
réelle de la question, ce que les tests isolés ne peuvent pas garantir.

`.env`, bases locales, uploads et environnements virtuels sont exclus de Git et du
contexte Docker. Ne pas enregistrer de clé ou de données sensibles dans les logs.
