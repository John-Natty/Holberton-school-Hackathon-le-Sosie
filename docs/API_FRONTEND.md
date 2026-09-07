# Contrat HTTP attendu par le frontend

Les routes viennent de SPEC.md, les types Expense et CalculationResult de OUTILS.md.
Les enveloppes ci-dessous sont le contrat HTTP intégré du palier 2. Les appels
utilisent la même origine que la page, sans clé ni secret dans JavaScript.

| Route | Envoi | Réponse JSON attendue (HTTP 2xx) |
| --- | --- | --- |
| `POST /imports` | multipart/form-data, champ `file` | `{ "imported_count": 3 }` (import atomique) |
| `GET /expenses` | — | `{ "expenses": [Expense] }` ou directement `[Expense]` |
| `POST /chat` | `{ "question": "Combien ai-je dépensé en alimentation ?" }` | `{ "calculation_id": 12 }` |
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
- `total_duration_ms` est persistée et disponible dans le détail : temps serveur
  depuis la réception de la question jusqu'à la comparaison (LLM inclus, hors
  écriture finale du calcul et transfert HTTP). Une ancienne ligne migrée contient
  `null`, affiché comme indisponible, jamais remplacé par zéro.
- L'enveloppe globale `ToolResult` est également acceptée : `{ "ok": true, "value": ... }`.
- Les textes `answer`, `message` et `error.message` doivent être en français.
- Refus d'import : HTTP 400/413/415/422. Erreur serveur : HTTP 5xx. Les erreurs HTTP,
  JSON invalide, réseau et délai de 30 secondes sont affichés sans afficher de page
  HTML serveur. Aucun renvoi automatique d'une écriture après expiration du délai.

Tous les contenus sont insérés avec `textContent`, jamais interprétés comme HTML,
code ou SQL. L'extension CSV et le format d'affichage ne remplacent aucune validation
serveur (type réel, taille, structure, valeurs, requêtes et cohérence des résultats).

## Erreurs et cohérence

Les erreurs applicatives utilisent `{ "ok": false, "error": { "message": "..." } }`
avec un statut HTTP non 2xx. Le frontend affiche ce message comme texte ; une page
HTML d'erreur conserve un message HTTP générique. Une clé Anthropic absente ou un
appel Claude refusé retourne HTTP 502 avec une explication sans clé ni réponse brute.

Un CSV invalide (y compris une seule ligne) est refusé entièrement, HTTP 422.
Aucune ligne n'est ajoutée ; un import valide retourne HTTP 201 et `imported_count`.
Limite : 2 Mio (HTTP 413). Les montants CSV sont en euros, avec au plus deux décimales ;
les montants JSON sont en centimes entiers.

Le backend compare des résultats complets et valides. Un calculateur en échec ou
un résultat mal formé entraîne `divergence`, sans chiffre final validé. `expenses`
est une liste directe contenant l'union des preuves des deux calculateurs valides.
Les imports sont bloqués pendant les deux lectures indépendantes afin de conserver
le même jeu de données. Le détail recalcule le verdict à partir des résultats
persistés, jamais avec un nouvel appel LLM ni un recalcul financier.

Les filtres de catégorie ignorent la casse Unicode : `alimentation` sélectionne
aussi `Alimentation`, et `santé` sélectionne `SANTÉ`. Les libellés enregistrés
restent inchangés. Les accents et les synonymes ne sont pas supprimés ou devinés.
Chaque calculateur conserve sa propre sélection et son propre cumul.
