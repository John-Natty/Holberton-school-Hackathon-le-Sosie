# Contrat HTTP attendu par le frontend

Les routes viennent de SPEC.md, les types Expense et CalculationResult de OUTILS.md.
Les enveloppes HTTP ci-dessous sont des **propositions d'intégration à convenir avec
Noham**, car les trois documents ne les définissent pas. Aucun endpoint métier
n'est simulé ni implémenté dans ce socle. Les appels utilisent la même origine que
la page, sans clé ni configuration secrète dans JavaScript.

| Route | Envoi | Réponse JSON attendue (HTTP 2xx) |
| --- | --- | --- |
| `POST /imports` | multipart/form-data, champ `file` | `{ "imported_count": 3 }` (objet, contenu facultatif) |
| `GET /expenses` | — | `{ "expenses": [Expense] }` ou directement `[Expense]` |
| `POST /chat` | `{ "question": "Combien ai-je dépensé en alimentation ?" }` | résultat ci-dessous, ou `{ "calculation_id": 12 }` |
| `GET /calculations/{calculation_id}` | — | résultat ci-dessous |
| `GET /health` | — | `{ "status": "ok" }` |

L'identifiant reçu de `/chat` déclenche la lecture du détail. Le calcul doit être
consultable immédiatement (pas de protocole de polling ajouté au palier 2).
Une précision se renvoie depuis `/chat` avec HTTP 200 :

```json
{"status":"needs_clarification","message":"Veuillez préciser la période que vous souhaitez analyser."}
```

L'utilisateur complète sa question puis la renvoie. Aucun historique de conversation
n'est supposé côté frontend.

Exemple de détail d'un calcul :

```json
{
  "answer": "Vous avez dépensé 42,50 € en alimentation.",
  "verdict": "concordance",
  "python": {
    "ok": true,
    "value": {"result_cents": 4250, "expense_ids": [1], "duration_ms": 3.4}
  },
  "sql": {
    "ok": true,
    "value": {"result_cents": 4250, "expense_ids": [1], "duration_ms": 1.2}
  },
  "total_duration_ms": 5.1,
  "expenses": [
    {"id": 1, "date": "2026-09-01", "description": "Carrefour", "category": "Alimentation", "amount_cents": 4250, "source_type": "csv"}
  ]
}
```

- `verdict` : `concordance` ou `divergence`, exclusivement décidé par le backend.
  Un verdict absent/inconnu est affiché comme non validé. Le frontend ne compare
  ni montants ni listes d'identifiants.
- `python` et `sql` acceptent les ToolResult de OUTILS.md ou leur valeur directe.
  Un échec utilise `{ "ok": false, "error": { "code": "...", "message": "..." } }`.
- `expenses` fournit les preuves du calcul, y compris les deux sélections si elles
  divergent. Les identifiants restent visibles si les détails manquent.
- La durée totale est facultative. Une donnée manquante n'est jamais remplacée par zéro.
- L'enveloppe globale `ToolResult` est également acceptée : `{ "ok": true, "value": ... }`.
- Les textes `answer`, `message` et `error.message` doivent être en français.
- Refus d'import : HTTP 400/413/415/422. Erreur serveur : HTTP 5xx. Les erreurs HTTP,
  JSON invalide, réseau et délai de 30 secondes sont affichés sans afficher de page
  HTML serveur. Aucun renvoi automatique d'une écriture après expiration du délai.

Tous les contenus sont insérés avec `textContent`, jamais interprétés comme HTML,
code ou SQL. L'extension CSV et le format d'affichage ne remplacent aucune validation
serveur (type réel, taille, structure, valeurs, requêtes et cohérence des résultats).
