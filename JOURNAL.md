# JOURNAL : Le Sosie

## 2026-09-07 · Palier 1 (Cadrage)

- Rédaction de `SPEC.md` : problème, user stories, hors-scope (10 items), happy path en 6 étapes, répartition du travail.
- Rédaction de `MENACES.md` v1 : sources d'entrée (question utilisateur, saisies, fichiers, images, résultats des calculateurs), canal, ce qui se passe si le canal ment, protection prévue.
- Rédaction de `OUTILS.md` : signatures typées complètes de `calculate_python`, `calculate_sql`, `get_expenses`, contrat `CalculationRequest` / `CalculationResult` / `ToolResult`.
- Choix retenu pour la carte bonus « Le non argumenté » : la ligne du hors-scope sur l'absence d'un troisième moteur d'arbitrage entre Python et SQL.

## 2026-09-07 - Palier 2 (Socle)

- Backend Flask mis en place avec SQLite.
- Import CSV avec validation et normalisation des dépenses.
- Calcul Python et calcul SQL indépendants.
- Comparaison du montant et des `expense_ids`.
- Endpoints disponibles : `/health`, `/imports`, `/expenses`, `/chat`, `/calculations/{id}`.
- Intégration de Claude pour transformer une question en opération structurée.
- Validation côté serveur des opérations, dates et paramètres retournés par le LLM.
- Utilisation de `Decimal` pour les montants financiers.
- Frontend créé avec import CSV, affichage des dépenses, question utilisateur et résultats Python / SQL.
- Harmonisation du contrat JSON entre frontend et backend.
- Gestion des concordances, divergences, erreurs et demandes de précision.
- Ajout de `.env.example`, Dockerfile, `compose.yaml` et README de lancement.
- SQLite stockée dans un volume Docker avec exécution du conteneur en utilisateur non root.
- Tests Python, JavaScript et navigateur ajoutés.
- Déploiement public réalisé sur Render avec Gunicorn.
- Correction du schéma JSON Anthropic pour les sorties structurées.
- Happy path prévu : CSV → SQLite → question → Claude → Python + SQL → comparaison → résultat affiché.

### Validation palier 2

- `.env.example` contient les variables nécessaires.
- `MENACES.md` décrit plusieurs canaux d'entrée et leurs risques.
- Le projet peut être lancé avec Docker à partir du README.
- Une URL publique de démonstration est disponible via Render.


## 2026-09-08 - Palier 3 (La boucle)

### Jonathan - frontend

- Ajout d'une section `Trace de l'agent`.
- Affichage du nom de l'outil réellement appelé.
- Affichage des arguments envoyés à l'outil.
- Affichage du statut et du résultat retourné.
- Gestion visuelle des erreurs d'outil.
- Support de plusieurs appels d'outil.
- Les traces sont affichées uniquement si elles proviennent du backend.
- Aucun appel d'outil n'est reconstruit ou simulé côté frontend.
- Toutes les données de trace sont affichées avec `textContent`.

### Bonus Streaming

- Ajout du mode `Exécution en direct (bonus)`.
- Le parcours classique reste utilisé par défaut.
- Ajout de `static/js/stream.js`.
- Lecture progressive avec `fetch()` et `response.body.getReader()`.
- Parseur SSE indépendant du rendu.
- Gestion prévue des événements :
  - `agent`
  - `tool_call`
  - `tool_result`
  - `final`
  - `error`
- Support de `call_id` pour relier un appel d'outil à son résultat.
- Aucun faux effet de streaming ou effet machine à écrire.
- Ajout d'un bouton permettant d'interrompre la lecture du flux.
- Tests du flux progressif ajoutés côté JavaScript et navigateur.

### Tests frontend palier 3

- 16 tests JavaScript validés.
- 68 tests Python validés.
- 3 tests navigateur validés.
- `git diff --check` validé.

### Reste à faire palier 3

- Noham : implémenter le véritable outil agent `verify_expenses`.
- Faire réellement appeler cet outil par l'agent.
- Faire remonter `tool_trace` depuis le backend.
- Ajouter `POST /chat/stream`.
- Émettre réellement les événements SSE au moment où les étapes sont exécutées.
- Tester volontairement l'échec d'un outil.
- Tester une requête non prévue.
- Tester une requête hostile.
- Faire la démo complète du checkpoint.
