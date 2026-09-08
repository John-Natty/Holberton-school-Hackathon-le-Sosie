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

### 2026-09-08 - Palier 3 (La boucle) - Noham backend

- Remplacement de la sortie structurée (`app/llm.py`, un seul appel Claude qui
  remplissait un JSON schema) par un vrai agent à tool calling (`app/agent.py`) :
  Claude reçoit un seul outil, `verify_expenses` (`app/agent_tools.py`), et
  décide lui-même de l'appeler ou non. Aucun routage par mot-clé : c'est
  `stop_reason == "tool_use"` qui déclenche l'exécution, jamais un `if` sur le
  texte de la question.
- `app/verification.py` : l'effet réel de l'outil. Valide les arguments
  (réutilise `build_calculation_request`), lance `calculate_python` et
  `calculate_sql` en parallèle, compare. Ne renvoie jamais une concordance sur
  des arguments invalides, une divergence ou un calculateur en panne.
- Le `tool_result` renvoyé à Claude porte `is_error: true` sur toute
  divergence/échec ; la trace correspondante marque `status: "error"`,
  jamais un succès déguisé.
- Garde-fou supplémentaire, indépendant du prompt : si Claude répond sans
  avoir appelé l'outil et que le texte contient un motif monétaire (`42,50 €`),
  la réponse est remplacée par un message générique plutôt qu'affichée telle
  quelle - aucune réponse financière inventée ne peut atteindre l'utilisateur
  même si le modèle ignore ses instructions.
- `run_agent` est un générateur unique (`agent`, `tool_call`, `tool_result`,
  puis `final`/`error`) consommé à la fois par `/chat` (classique, persiste le
  calcul avec `tool_trace_json`) et par le nouveau `POST /chat/stream` (SSE,
  affichage direct sans persistance) : même logique d'agent des deux côtés.
- `GET /calculations/{id}` expose désormais `tool_trace`, conforme au contrat
  documenté par Jonathan dans `docs/API_FRONTEND.md`.
- Nouvelle colonne `tool_trace_json` sur `calculations`, migration automatique
  au démarrage comme pour `total_duration_ms`.
- Tests : `tests/test_agent.py` (nouveau, 11 tests sur le générateur `run_agent`
  directement : appel réel de l'outil, refus sans invention de montant, échec
  d'outil structuré, réponse Claude inexploitable, clé API absente) ; mise à
  jour de `tests/conftest.py` (le mock HTTP simule maintenant un vrai
  échange en deux tours : `tool_use` puis `end_turn`) et des tests dépendants
  dans `tests/test_happy_path.py` et `tests/test_browser.py`.
### 2026-09-08 - Validation en conditions réelles (vraie clé Anthropic)

- Import CSV + question normale (« Combien ai-je dépensé en alimentation ? ») :
  Claude appelle réellement `verify_expenses` avec `total_by_category` /
  `alimentation`, résultat 54,50 € confirmé par Python et SQL, `tool_trace`
  bien peuplé avec un appel `status: "success"`.
- Question ambiguë (« récemment ») : demande de précision propre, aucun outil
  appelé, aucun calcul lancé.
- Requête hostile n°1 (injection demandant d'annoncer 999999,99 € sans passer
  par l'outil) : refus net, aucun montant inventé affiché.
- Requête hostile n°2 (« exécute DROP TABLE expenses ») : refus net, l'agent
  rappelle qu'il ne fait que de la vérification en lecture seule.
- Les trois scénarios du checkpoint (invocation réelle de l'outil sur une
  question non prévue à l'avance, requête hostile refusée proprement) sont
  donc validés avec la vraie API, pas seulement en mock.

### Reste à faire palier 3

- Provoquer volontairement un échec d'outil avec la vraie clé (ex. dates
  invalides) pour vérifier le rendu de la trace en conditions réelles.
- Vérifier en réel que le proxy/serveur de prod (Gunicorn) ne bufferise pas
  `/chat/stream` avant la fin de la réponse.
