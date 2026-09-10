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
La réponse HTTP externe de Claude est simulée ; les contrôles locaux réels de
langue et de modération sont exécutés sans téléchargement ni modèle neuronal.
Les tests marqués `local_moderation` couvrent les formulations dangereuses et
les contre-exemples légitimes. Les tests de divergence remplacent explicitement
un calculateur. Aucune clé ni dépense réelle n'est utilisée. Les bases de test
sont temporaires.

## Contrôles locaux avant traitement

La validation d'entrée est suivie de la détection locale de langue avec
[langdetect 1.0.9](https://pypi.org/project/langdetect/1.0.9/), puis de règles de
modération contextuelles en Python standard. Claude n'est appelé qu'après ces
contrôles et celui de l'état de l'agent. Les refus conservent leurs contrats
HTTP/SSE et ne consomment aucun appel, token Anthropic ou coût externe.

La langue utilise les petits profils statistiques de n-grammes livrés avec la
bibliothèque, sans ONNX, Torch, Transformers ou tokenizer neuronal. Une seule
fabrique de profils est initialisée sous verrou par worker ; les détecteurs
propres aux requêtes ne gardent aucun texte dans cette fabrique. La graine est
fixée pour rendre le résultat reproductible. Seule une langue étrangère avec
une confiance élevée est refusée ; les expressions latines très courtes restent
ambiguës. La présence de noms propres et termes techniques n'est pas un critère
de refus. La détection statistique peut néanmoins se tromper sur un texte mixte.

La modération associe action demandée, objet dangereux et, si nécessaire,
caractère illicite dans une même proposition. Elle traite les négations et les
contextes de prévention, droit, histoire, soin et cybersécurité autorisée.
Un contexte légitime dans une phrase n'exempte pas une instruction dangereuse
séparée ; demander une méthode opérationnelle après un prétexte de prévention
reste bloquant pour les formulations reconnues. Les descriptions nominales
courantes des CSV sont aussi contrôlées. Les douze familles de risques restent
présentes, avec un message de soutien pour l'automutilation.

Cette approche déterministe est légère et testable, mais sa couverture est plus
étroite que celle d'un classificateur sémantique : les règles décrivent des
formulations explicites françaises et quelques équivalents anglais, sans
comprendre toutes les paraphrases, autres langues ou obfuscations. Des faux
positifs et faux négatifs restent possibles. Les tests constituent un corpus de
régression, pas une garantie de détection générale. Les fichiers n'ont pas de
barrière de langue et cette limite linguistique s'applique donc aussi aux CSV.

Aucun poids de modération n'est téléchargé ou chargé, au démarrage ou en requête.
L'ancienne session ONNX mDeBERTa, son tokenizer et les profils Lingua ont été
retirés. Les quelque 339 Mo de poids ONNX, les allocations d'inférence et les
bibliothèques natives associées ne sont plus nécessaires. La mémoire totale
reste à mesurer sur Render ; aucune garantie chiffrée de RSS n'est avancée.
Gunicorn conserve **un worker et quatre threads**, sans changement d'offre Render.

Le contrôle garde un budget coopératif de 12 secondes par question et 20 secondes
par fichier. Une erreur du filtre, des profils de langue indisponibles ou une
analyse non terminée entraînent HTTP 503, sans appel Claude ni insertion.
Les fichiers multipart restent en mémoire sous la limite de 2 Mio. Le CSV entier
passe par la validation structurelle et la modération de tous les champs libres,
puis la normalisation et une insertion atomique. Aucun format supplémentaire
n'est accepté. Tout futur format devra avoir son propre contrôle avant
extraction/OCR, exploitation ou persistance. Les journaux de blocage restent
génériques, sans contenu utilisateur.

Une reconstruction Docker à partir du nouveau `requirements.txt` n'installe plus
`lingua-language-detector`, `onnxruntime`, `tokenizers` ni leurs dépendances ML
transitives. Dans un environnement virtuel existant, `pip install -r` ne supprime
pas les anciens paquets : préférer un environnement neuf pour reproduire le
déploiement. L'ancien dossier `.local_models/` est inutilisé et reste exclu de
Git et du contexte Docker ; `MODERATION_MODEL_DIR` n'est plus utilisé.

Pour les vérifications locales séparées :

```sh
python -m pytest tests/test_question_language.py tests/test_content_moderation.py -q
```

Ces tests exécutent les vrais filtres légers et contrôlent aussi l'absence d'import
de dépendances ML lourdes. Ils ne nécessitent ni clé API ni poids à provisionner.
La suite complète reste celle indiquée plus haut.

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
