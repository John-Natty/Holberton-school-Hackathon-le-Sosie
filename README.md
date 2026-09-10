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
python scripts/prepare_moderation.py
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
La réponse HTTP externe de Claude est simulée ; les tests de protocole isolent
aussi l'inférence de modération pour rester rapides. Les tests marqués
`local_moderation` utilisent les vrais poids locaux et les contre-exemples de
prévention/droit/recherche. Les tests de divergence remplacent explicitement un
calculateur. Aucune clé ni dépense
réelle n'est utilisée. Les bases de test sont temporaires.

## Contrôles locaux avant traitement

La validation d'entrée est suivie de la détection locale de langue avec
[Lingua](https://github.com/pemistahl/lingua-py), puis de la modération d'intention
avec le modèle multilingue non génératif
[mDeBERTa NLI](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli).
Claude n'est appelé qu'après ces contrôles et celui de l'état de l'agent.
Les textes courts ambigus, noms propres et termes techniques ne sont pas refusés
sur la seule présence de mots étrangers. Un refus local ne consomme aucun appel,
token Anthropic ou coût externe.

`scripts/prepare_moderation.py` télécharge une fois les poids publics quantifiés
et leur tokenizer (environ 355 Mo), avec révision et empreintes SHA-256 figées.
Docker le fait pendant la construction. Aucun téléchargement, service distant
ou appel Anthropic n'intervient pendant la modération ; aucune donnée utilisateur
n'est envoyée au dépôt de modèles. `MODERATION_MODEL_DIR` permet de fournir un
dossier local provisionné hors ligne. Les poids ne sont pas versionnés dans Git.

Prévoir la mémoire pour ONNX et le tokenizer en plus de Flask (au moins 1 Gio
recommandé, à mesurer sur l'hébergement cible) : le plan gratuit de 512 Mio
mentionné dans la configuration Render n'est pas qualifié pour cette couche.
Une seule inférence s'exécute à la fois, sur un thread CPU. Le contrôle dispose
d'un budget coopératif de 12 secondes par question et 20 secondes par fichier ;
un fichier très volumineux peut donc être
refusé techniquement même sous la limite de 2 Mio. Modèle absent/invalide, attente
ou analyse trop longue : HTTP 503, aucun appel Claude ni insertion. Il n'y a pas
de repli qui contourne silencieusement la modération.

Les catégories sont des descriptions d'intention, comparées sémantiquement aux
textes, et non des mots interdits. Les intentions légitimes de prévention, droit,
recherche, soin et cybersécurité autorisée sont comparées aussi. Ce classificateur
reste probabiliste : il peut produire des faux positifs et manquer des demandes
obfusquées. La qualification des formulations et des seuils sur un corpus
indépendant reste nécessaire ; il ne constitue pas une garantie générale de
détection de tout contenu illégal.

Les fichiers multipart restent en mémoire. Le CSV entier passe par la validation
structurelle et la modération de tous les champs, puis la normalisation et une
insertion atomique. Aucun format supplémentaire n'est accepté. Tout futur format
devra disposer de son propre contrôle avant extraction/OCR, exploitation ou
persistance. Les journaux ne contiennent que les événements génériques de blocage.

Pour les vérifications locales séparées :

```sh
python -m pytest tests/test_question_language.py tests/test_content_moderation.py -m 'not local_moderation' -q
python -m pytest tests/test_content_moderation.py -m local_moderation -q
```

La seconde commande qualifie réellement le classificateur et peut prendre plus
de temps. La suite complète reste celle indiquée plus haut.

Le test final avec Claude réel reste le parcours Docker et CSV décrit plus haut,
avec une vraie clé. Il vérifie aussi l'accès au modèle, les crédits et l'interprétation
réelle de la question, ce que les tests isolés ne peuvent pas garantir.

`.env`, bases locales, uploads et environnements virtuels sont exclus de Git et du
contexte Docker. Ne pas enregistrer de clé ou de données sensibles dans les logs.

## Évaluation automatisée (bonus palier 4)

`scripts/eval_agent.py` rejoue dix scénarios contre une instance en mémoire de
l'application (aucun serveur à lancer) : import CSV, question normale,
clarification, deux injections hostiles, divergence provoquée, opération
désactivée, arrêt/redémarrage de l'agent, clé API absente, lecture du journal.
Affiche PASS/FAIL/SKIP puis un score, code de sortie 1 si un scénario échoue.

```sh
. .venv/bin/activate
python scripts/eval_agent.py
```

Sans `ANTHROPIC_API_KEY` dans l'environnement, les scénarios nécessitant un
vrai appel Claude sont marqués `SKIP` plutôt que `FAIL` : renseigner la clé
(par exemple `set -a; . ./.env; set +a`) pour une évaluation complète en 10/10.

## URL publique de démonstration

Le [guide Render](docs/DEPLOIEMENT_RENDER.md) décrit la publication depuis GitHub
avec `render.yaml`. Le conteneur utilise Gunicorn ; Render fournit `PORT` (5000 par
défaut en local). La configuration gratuite convient à une démonstration sur
**données fictives partagées** ; SQLite n'y est pas persistante. La clé Anthropic
se configure uniquement dans les variables d'environnement du service.
