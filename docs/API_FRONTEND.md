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

## Palier 3 : trace des appels d'outil

Le détail `GET /calculations/{calculation_id}` (ou une réponse de calcul directe
à `POST /chat`) peut fournir `tool_trace`, un tableau ordonné de tous les appels
réellement effectués par l'agent côté backend. Exemple :

```json
{
  "tool_trace": [
    {
      "tool": "verify_expenses",
      "arguments": {
        "operation": "total_by_category",
        "category": "Alimentation",
        "start_date": null,
        "end_date": null
      },
      "status": "success",
      "result": { "verdict": "concordance", "result_cents": 7250 }
    },
    {
      "tool": "verify_expenses",
      "arguments": { "operation": "total", "category": null, "start_date": null, "end_date": null },
      "status": "error",
      "error": { "code": "tool_error", "message": "Le calcul n'a pas pu être validé." }
    }
  ]
}
```

- Chaque appel possède son propre bloc : nom `tool`, objet `arguments`, `status`
  (`success` ou `error`), puis `result` en cas de succès ou `error` en cas d'échec.
- Toutes les clés et valeurs des arguments sont visibles, y compris les chaînes,
  nombres, booléens et `null`. Les résultats supplémentaires restent visibles ;
  les objets et tableaux imbriqués sont affichés en JSON comme texte.
- Seul `result_cents` est formaté en euros pour l'affichage. Le verdict est affiché
  tel que reçu, sans comparaison ni décision financière côté navigateur.
- Un échec affiche son code et son message en rouge, sans afficher `result`, même
  si ce champ est présent par erreur. Un statut inconnu n'est pas présenté comme
  un succès. Une valeur monétaire invalide est affichée « Non disponible ».
- Champ absent, `null`, tableau vide ou type invalide : section masquée. La trace
  précédente est effacée lors d'une nouvelle question ou d'un import réussi.
- Tous les contenus utilisent `textContent`. Aucune trace n'est reconstruite à
  partir de `python`, `sql`, `request` ou `verdict`.

État vérifié pour cette intégration : `dev` à `61ef057` et `noham` à `c79469b`
ne fournissent pas encore `tool_trace`. Noham doit produire la trace des appels
réels et la rendre disponible dans le détail du calcul pour le parcours actuel
`POST /chat` → `GET /calculations/{calculation_id}`. Aucun backend de production
ni tool calling Anthropic n'est modifié par cette intégration frontend.
Le test navigateur du contrat utilise une fixture de réponse côté Flask ; il
ne démontre pas encore l'exécution réelle d'un appel d'outil par l'agent.

## Bonus palier 3 : `/chat/stream` (contrat provisoire)

La case **Exécution en direct (bonus)** active un parcours supplémentaire. Elle
est décochée par défaut : le parcours `/chat` puis `/calculations/{id}` est conservé.
Le frontend envoie `POST /chat/stream` avec `Content-Type: application/json`,
`Accept: text/event-stream` et `{"question":"..."}`. Il lit le corps via
`fetch()` et `response.body.getReader()`, sans temporisation d'affichage.

Le serveur doit répondre HTTP 200 avec `Content-Type: text/event-stream; charset=utf-8`.
Chaque événement se termine par une ligne vide. Les données JSON peuvent occuper
plusieurs lignes, chacune préfixée par `data:`. Exemple de flux :

```text
event: agent
data: {"message":"Analyse de la demande..."}

event: tool_call
data: {"call_id":"call_1","tool":"verify_expenses","arguments":{"operation":"total_by_category","category":"Alimentation","start_date":null,"end_date":null}}

event: tool_result
data: {"call_id":"call_1","tool":"verify_expenses","status":"success","result":{"verdict":"concordance","result_cents":7250}}

event: final
data: {"answer":"Vous avez dépensé 72,50 € dans la catégorie Alimentation."}

```

- `agent` : message affiché dès réception d'un événement complet. Plusieurs
  messages peuvent être envoyés et restent visibles dans l'ordre de réception.
- `tool_call` : crée un bloc avec `tool` (texte) et `arguments` (objet), sans
  présumer du succès. Les valeurs `null`, booléennes et numériques sont conservées.
- `tool_result` : complète le bloc correspondant. `status: "success"` affiche
  `result` ; `result_cents` est seulement formaté en euros. `status: "error"`
  affiche `error: {"code":"tool_error","message":"..."}` en rouge et ignore
  tout champ `result`. Cette erreur d'outil n'arrête pas à elle seule le flux.
- `call_id` : chaîne non vide unique par appel, identique dans `tool_call` et
  `tool_result`. Facultatif pour les exemples séquentiels : sans identifiant,
  un seul appel sans identifiant du même outil doit être en attente. Pour des
  appels concurrents au même outil, fournir les identifiants. Un résultat orphelin,
  dupliqué ou ambigu signale une erreur de protocole et ne crée aucun appel.
- `final` : `answer` obligatoire, affichée dans la zone directe ; termine la lecture.
  Ce contrat transmet la réponse finale complète. Pour un affichage mot à mot,
  un contrat de fragments provenant réellement du serveur reste à définir.
  Le frontend ne déduit ni verdict global ni résultats Python/SQL de cette réponse.
- `error` : `{"message":"Le calcul n'a pas pu être validé."}`, affiché en rouge ;
  termine la lecture, même s'il arrive avant tout appel. Aucun événement ultérieur
  n'est affiché après `final` ou `error`.

Le parseur est indépendant du rendu `handleStreamEvent(type, payload)` : il accepte
LF, CRLF et CR, les commentaires SSE, plusieurs événements dans un chunk, un
événement sur plusieurs chunks et les caractères UTF-8 coupés entre octets.
Les commentaires, champs SSE non utilisés (`id`, `retry`) et types d'événement
inconnus sont ignorés. Une dernière trame sans ligne vide n'est pas dispatchée.
Une fermeture sans `final` ou `error`, un JSON invalide, une erreur HTTP, un type
MIME incorrect ou une rupture réseau sont signalés dans le statut de la question,
sans les présenter comme événements de l'agent. Les événements déjà reçus restent
visibles. Aucun réessai ni repli automatique vers `/chat` ne réexécute la question.
Le bouton **Arrêter la lecture du flux** interrompt la requête navigateur ; il
ne garantit pas l'arrêt du travail côté serveur. Une nouvelle question ou un
import réussi efface l'affichage direct précédent.

Tous les contenus reçus sont insérés par `textContent`. Aucun `tool_call` n'est
reconstruit à partir d'un résultat ou d'une réponse finale.

**À fournir par Noham :** implémenter `/chat/stream`, émettre les événements au
moment des véritables étapes de l'agent et des outils, assurer leur corrélation,
puis terminer par `final` ou `error`. Le serveur et son proxy doivent transmettre
les morceaux progressivement, sans mise en tampon jusqu'à la fin. Cette tâche
ne modifie pas le backend agent. Les flux des tests sont des fixtures explicites,
pas une preuve d'intégration du streaming Anthropic.
