# Le Sosie

Le Sosie permet d'importer ses dépenses et de poser une question en français.
Deux calculateurs indépendants, Python et SQL, doivent fournir leurs résultats et
leurs preuves ; le backend décide de leur concordance.

## Démarrage rapide

Prérequis : Git, Docker et Docker Compose v2.

```sh
git clone https://github.com/John-Natty/Holberton-school-Hackathon-le-Sosie.git
cd Holberton-school-Hackathon-le-Sosie
cp .env.example .env
docker compose up --build
```

Ouvrir **http://localhost:5000**. Arrêter avec `Ctrl+C`, puis `docker compose down`.
Le code présenté ici doit être présent dans la copie clonée pour utiliser ce parcours.

**État du palier 2 :** l'interface est lançable. Seuls `/` et les fichiers statiques
sont servis par `app.py`. Les routes métier restent à développer par Noham : tant
qu'elles sont absentes, l'interface affiche « Endpoint indisponible » et aucun
import ni calcul réel ne peut aboutir. Aucun résultat fictif n'est renvoyé.

## Configuration et intégration

`.env.example` contient uniquement `FLASK_APP=app:app` (point d'entrée Flask) et
`APP_PORT=5000` (port local Docker). Compose transmet `.env` au conteneur.
Si le port change, adapter l'URL locale. Aucun fournisseur LLM ni chemin SQLite
n'est imposé avant l'implémentation du backend ; ajouter alors ses variables
réellement nécessaires à `.env.example`, sans secret.

Noham peut ajouter ses routes à l'application Flask ou reprendre la route `/`,
`templates/` et `static/` dans son application, puis adapter `FLASK_APP`.
Le [contrat HTTP provisoire](docs/API_FRONTEND.md) décrit les réponses attendues,
les demandes de précision et les détails de calcul. Les appels restent sur la même
origine. Docker utilise le serveur Flask pour cette démonstration locale, sans debug.
Le stockage persistant sera à configurer avec le backend SQLite.

## Essai et validations

Le CSV de référence utilise les montants en euros :

```csv
date,description,categorie,montant
2026-09-01,Carrefour,Alimentation,42.50
2026-09-02,Essence,Transport,65.00
```

Sélectionner un CSV, cliquer sur « Importer », puis poser une question. Une fois le
backend intégré, vérifier les montants, le verdict et les preuves de chaque méthode.
Avant intégration, vérifier les messages d'indisponibilité et les champs du formulaire.

Sans Docker (Python 3.12 ou supérieur) :

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
flask --app app:app run --no-debugger --no-reload
```

Validations (Node.js 18 ou supérieur pour les tests JavaScript) :

```sh
node --check static/js/app.js
node --test tests/frontend.test.cjs
python -m unittest discover -s tests
docker compose --env-file .env.example config --quiet
```

Les scénarios JavaScript utilisent des réponses isolées de test, jamais servies par
l'application. Les fichiers `.env`, bases locales et uploads sont exclus de Git
et du contexte Docker. Ne pas placer de dépenses sensibles dans les logs.
