# JOURNAL : Le Sosie

## 2026-09-07 · Palier 1 (Cadrage)

- Rédaction de `SPEC.md` : problème, user stories, hors-scope (10 items), happy path en 6 étapes, répartition du travail.
- Rédaction de `MENACES.md` v1 : sources d'entrée (question utilisateur, saisies, fichiers, images, résultats des calculateurs), canal, ce qui se passe si le canal ment, protection prévue.
- Rédaction de `OUTILS.md` : signatures typées complètes de `calculate_python`, `calculate_sql`, `get_expenses`, contrat `CalculationRequest` / `CalculationResult` / `ToolResult`.
- Choix retenu pour la carte bonus « Le non argumenté » : la ligne du hors-scope sur l'absence d'un troisième moteur d'arbitrage entre Python et SQL.

## 2026-09-07 · Palier 2 (Socle) - backend

- Backend Flask créé (`app/`) : `db.py` (schéma SQLite `expenses` + `calculations`), `models.py` (validation/normalisation), `csv_import.py` (import CSV avec lignes rejetées explicites).
- Implémentation des trois outils du palier 1 : `calculate_python`, `calculate_sql` (isolés, chacun avec sa propre connexion SQLite dans son propre thread, exécution en parallèle), `get_expenses`.
- Comparateur : concordance uniquement si montant ET `expense_ids` identiques.
- `POST /chat` : question en langage naturel envoyée à Claude (sortie structurée JSON) pour produire un `CalculationRequest`, ou une demande de clarification si la question est ambiguë. Toute sortie du LLM est revalidée côté serveur avant d'être exécutée.
- Modèle retenu pour le parsing de la question : `claude-sonnet-5`.
- Endpoints livrés : `GET /health`, `POST /imports`, `GET /expenses`, `POST /chat`, `GET /calculations/{id}`.
- Tests (`tests/test_happy_path.py`) : import CSV, happy path complet CSV → question → Python + SQL → comparaison, demande de clarification, divergence détectée sur des `expense_ids` différents. Le LLM est mocké faute de clé API en environnement de dev ; à revalider avec un appel réel avant la démo du palier 2.

### Reste à faire (palier 2)

- Jonathan : frontend minimal (import CSV, zone de question, affichage dépenses/résultats), `.env.example` (dont `ANTHROPIC_API_KEY`), Docker, README de lancement.
- En commun : test de clone propre, vérification du lancement en moins de 5 minutes, préparation de la démo.
