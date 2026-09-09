# Contrat HTTP attendu par le frontend

Les routes viennent de SPEC.md, les types Expense et CalculationResult de OUTILS.md.
Les enveloppes ci-dessous sont le contrat HTTP intégré du palier 2. Les appels
utilisent la même origine que la page, sans clé ni secret dans JavaScript.

| Route | Envoi | Réponse JSON attendue (HTTP 2xx) |
| --- | --- | --- |
| `POST /imports` | multipart/form-data, champ `file` | `{ "imported_count": 3 }` (import atomique) |
| `GET /expenses` | — | `{ "expenses": [Expense] }` ou directement `[Expense]` |
| `POST /chat` | `{ "question": "Combien ai-je dépensé en alimentation ?" }` | `{ "calculation_id": 12, "request_info": { ... } }` (voir Palier 5) |
| `GET /calculations/{calculation_id}` | — | résultat ci-dessous |
| `GET /health` | — | `{ "status": "ok" }` |
| `GET /agent/state` | — | `{ "status": "running", "reason": null }` ou `{ "status": "stopped", "reason": "..." }` |
| `POST /agent/state` | `{ "status": "running" }` ou `{ "status": "stopped" }` | le nouvel état au même format |
| `GET /agent/logs?limit=50` | — | `{ "logs": [{ "timestamp": "2026-09-08T10:15:00.000Z", "level": "INFO", "message": "..." }], "count": 1 }` |

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

## Palier 4 : contrôle de l’agent

La carte « Contrôle de l’agent » charge l’état uniquement depuis la route réelle
`/agent/state`. Le frontend ne déduit et ne simule aucun état. Les deux valeurs
acceptées sont `running` et `stopped`; toute autre réponse est signalée comme
indisponible. Le bouton d’arrêt envoie `stopped` et celui de redémarrage envoie
`running`. Après chaque action acceptée, l’état est relu depuis le backend.

Le backend écrit le journal à côté de la base SQLite et expose au plus ses 50
dernières lignes via `GET /agent/logs`. Le paramètre `limit` est optionnel et
doit être compris entre 1 et 50. Un fichier encore absent produit une liste
vide ; un fichier inaccessible produit une erreur JSON 503. Les secrets et
formats usuels de clés sont expurgés avant toute réponse HTTP.

Le panneau frontend charge `GET /agent/logs?limit=50` au démarrage et après
chaque STOP/START. Il ne lit jamais directement le fichier.
Les entrées fournies possèdent `timestamp`, `level` et `message`, déjà expurgés
de toute clé API, jeton ou secret. Le rendu existant peut les valider, les trier
du plus récent au plus ancien et les insérer uniquement avec `textContent`.

Une réponse HTTP 404 ou 503 d’une route de contrôle affiche « Contrôle indisponible »
et ne déclenche aucun état de remplacement. Si l’état ne peut pas être chargé, les
deux actions restent désactivées. Les erreurs du panneau n’empêchent pas le chat,
le flux SSE, la trace, les imports CSV ou les opérations de test de fonctionner.

## Présentation du tableau de bord

L'interface est harmonisée en français et conserve les mêmes routes HTTP.
La carte « Réponse de Le Sosie » s'affiche sous la question. La comparaison Python/SQL
et les preuves restent accessibles dans la colonne droite, sous « Voir les détails ».
Le montant de synthèse reprend le résultat Python fourni par le backend uniquement
avec un verdict `concordance` et des résultats numériques disponibles pour les deux
méthodes. Aucun cumul ni comparaison métier n'est ajouté. Le nombre de dépenses
correspond à la longueur des `expense_ids` de ce résultat ; la catégorie provient
de `request.category`. Une donnée manquante n'est pas déduite de la question.
En cas de divergence, la synthèse chiffrée est masquée et les deux résultats restent
consultables. Une réponse `final` du flux apparaît aussi dans la carte de réponse,
sans inventer les informations de synthèse absentes de l'événement.

La recherche (description, catégorie, date ou identifiant) et le filtre de catégorie
s'appliquent uniquement à l'affichage de la liste chargée. Ils ne modifient ni les
dépenses en base ni le périmètre d'une question. Le dépôt d'un fichier sélectionne
un CSV ; le bouton « Importer » confirme toujours son envoi. Seul CSV est annoncé
comme pris en charge. Les suggestions disponibles remplissent le champ de question
sans l'envoyer ; les opérations non implémentées restent désactivées et marquées
« à venir ».

Le flux direct est une option discrète sous le champ de question. Ses événements et
la trace classique utilisent la même carte « Trace de l'agent », sans carte streaming
séparée. L'état vide de cette carte est un texte d'aide, jamais une trace fabriquée.
La mascotte SVG est un visuel décoratif local, indépendant des données du serveur.

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
- Toutes les clés et valeurs publiques des arguments sont visibles, y compris les chaînes,
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

Mise à jour : le backend fournit désormais `tool_trace` pour de vrai. `/chat`
utilise un agent avec le tool calling Anthropic réel (`app/agent.py`, outil
unique `verify_expenses` défini dans `app/agent_tools.py`) : Claude décide
d'appeler l'outil ou non, le backend exécute alors `calculate_python` et
`calculate_sql` puis compare, et chaque appel réel est ajouté à la trace
persistée avec le calcul (`GET /calculations/{calculation_id}`).
Un argument invalide ou une divergence n'est jamais présenté comme un succès :
la trace marque l'appel `status: "error"`, et `tool_result` est renvoyé à
Claude avec `is_error: true`. `test_browser_tool_trace_contract` reste une
fixture HTTP pour valider le rendu ; `tests/test_agent.py` et
`tests/test_happy_path.py` exercent le vrai appel d'outil (SDK réel, seul le
HTTP externe d'Anthropic est simulé).

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
- `final` : `answer` obligatoire ; le détail complet est ajouté si un calcul a eu lieu (voir ci-dessous). Termine la lecture.
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

Mise à jour : `POST /chat/stream` utilise le même agent que `/chat` et transmet
les étapes réelles au fil de leur exécution. Quand un calcul a été effectué,
l'événement `final` contient désormais le détail complet du calcul persisté :
`id`, `answer`, `request`, `verdict`, `python`, `sql`, `expenses`, `tool_trace`
et `total_duration_ms`. Il réutilise exactement la réponse de
`GET /calculations/{id}`, sans relancer l'agent ni les calculateurs. La réponse
vérifiée et la comparaison sont donc identiques au parcours classique pour les
mêmes arguments et données. La durée mesure l'exécution propre à chaque requête.

Sans calcul publié (précision ou refus), `final` fournit `answer`, `status` et
`request_info` ;
aucune comparaison n'est inventée. Le frontend reste compatible avec ce format
minimal. Les étapes directes restent visibles dans leur timeline, sans dupliquer
la trace persistée à la fin. La carte « Trace de l'agent » est repliée par défaut
et peut être ouverte ou refermée au clavier ou à la souris, y compris pendant
la lecture du flux. Replier la carte n'interrompt pas le flux.

## Palier 5 : informations de la dernière requête

Le bouton **Infos requête**, à droite des suggestions sous le champ de question,
ouvre et referme le panneau **Informations de la requête**, intégré à la carte
de question. Il est désactivé avant le premier envoi et le panneau est fermé par
défaut. Le bouton natif fonctionne au clic, avec Entrée ou Espace ;
`aria-expanded` reflète l'ouverture et `aria-controls` désigne le panneau.
L'arrivée d'une réponse ne l'ouvre pas automatiquement. Le choix d'ouverture est
conservé entre les requêtes, et les données sont actualisées même lorsqu'il est
fermé. L'ouverture et la fermeture ne déclenchent aucun appel réseau.
Sur mobile, le contenu reste dans le flux de la carte, sans superposition.
Le panneau présente séparément l’état de réponse, la confiance, les compteurs
et le **coût de la dernière requête**. Chaque valeur absente, `null`, inconnue ou
mal typée affiche exactement **Non disponible**. Les zéros explicitement fournis
restent visibles. Aucun total, coût, appel ou niveau de confiance n’est calculé
par le navigateur : pas de chronomètre local, de comptage de la trace, de somme
des tokens, de tarif modèle, de conversion de devise ou d’analyse du texte.

### Disponibilité réelle et champs optionnels

Le backend fournit maintenant `request_info.metrics`, `request_info.cost` et
`request_info.usage_complete` à partir des usages réellement retournés par
Anthropic. Les détails d’agrégation, de cache et de persistance sont décrits
dans la section bonus ci-dessous. `total_duration_ms`, `verdict` et
`status: "needs_clarification"` conservent leur contrat existant.
La confiance de vérification ajoutée dans `dev` est exposée sous
`request_info.confidence: "high"` lorsque le backend confirme une concordance,
et `low` en divergence. Elle exprime le résultat de la double vérification,
pas un score de certitude fourni par Claude. Le champ historique à la racine
`confidence` conserve les valeurs `haute`/`aucune` dans le détail du calcul.
Les réponses terminales courantes fournissent aussi `status` à la racine et
dans `request_info`, avec la confiance structurée suivante :

| Statut | Confiance | Origine |
| --- | --- | --- |
| `verified` | `high` | Concordance Python/SQL confirmée par le backend |
| `unverified` | `low` | Divergence ou vérification non validée |
| `needs_clarification` | `uncertain` | Décision explicite de précision par Claude |
| `security_refusal` | `refused` | Décision explicite de refus de sécurité par Claude |
| `refused` | `refused` | Refus hors sécurité, par exemple demande hors périmètre |
| `error` | `error` | Erreur technique, protocole invalide ou annulation |

Le contrat interne de fin de tour Claude est un objet JSON strict
`{"answer": "...", "response_status": "..."}`. Les statuts non financiers
ci-dessus sont transmis explicitement ; `calculation` demande la restitution
d'un résultat de `verify_expenses`, dont le backend détermine seul le statut
`verified`/`unverified`. Un JSON invalide, un champ manquant, supplémentaire,
dupliqué ou un statut inconnu donne une erreur technique avec la consommation
déjà reçue. Aucun mot de la question ou du texte de réponse ne détermine le statut.
Le garde-fou existant contre les montants sans vérification filtre uniquement
le contenu affiché ; il ne change jamais la classification.

Précisions et refus restent HTTP 200 : `message` dans `/chat`, `answer` dans
l'événement SSE `final`, avec les mêmes statuts, confiance, métriques et coût.
Ils ne publient aucun détail financier validé, même après un appel d'outil.
Les erreurs techniques conservent les codes HTTP existants, ou un événement
SSE `error` si le flux est déjà ouvert. Aucun niveau `medium` n'est produit.

Aucune nouvelle route n’est ajoutée ou appelée. Les informations de consommation
sont présentes dans les réponses existantes :

- `POST /chat` : calcul direct, identifiant de calcul, précision ou refus ;
- `GET /calculations/{calculation_id}` : détail persisté ;
- événements SSE `final` et `error` de `POST /chat/stream` ;
- erreurs JSON HTTP, y compris lors de l’ouverture du flux SSE.

Exemple de contrat frontend complet (les champs de confiance et de statut restent
optionnels ; ce premier exemple n’est pas une mesure de consommation réelle) :

```json
{
  "answer": "Réponse du serveur.",
  "request_info": {
    "status": "verified",
    "confidence": "high",
    "metrics": {
      "total_duration_ms": 1234.56789,
      "calls": 6,
      "tool_calls": 2,
      "model_calls": 4,
      "input_tokens": 100,
      "output_tokens": 20,
      "total_tokens": 120
    },
    "cost": { "amount": "0.00123000", "currency": "USD" }
  }
}
```

| Champ dans `request_info` | Type / valeurs acceptées | Rendu |
| --- | --- | --- |
| `status` | `verified`, `unverified`, `needs_clarification`, `security_refusal`, `refused`, `error` | État explicite, voir ci-dessous |
| `confidence` | `high`, `medium`, `low`, `uncertain`, `insufficient_information`, `refused`, `error` | Confiance élevée, moyenne, faible ; incertitude / information insuffisante ; refus ; erreur |
| `metrics.total_duration_ms` | Nombre JSON fini ≥ 0 | Valeur reçue suivie de `ms`, sans arrondi ajouté |
| `metrics.calls` | Entier JSON sûr ≥ 0 | Nombre total d’appels effectué, fourni par le backend |
| `metrics.tool_calls` | Entier JSON sûr ≥ 0 | Nombre d’appels outil |
| `metrics.model_calls` | Entier JSON sûr ≥ 0 | Nombre d’appels modèle |
| `metrics.input_tokens` | Entier JSON sûr ≥ 0 | Tokens d’entrée |
| `metrics.output_tokens` | Entier JSON sûr ≥ 0 | Tokens de sortie |
| `metrics.total_tokens` | Entier JSON sûr ≥ 0 | Total reçu, jamais remplacé par input + output |
| `cost.amount` | Chaîne décimale positive ou nulle, motif `^\d+(?:\.\d+)?$` | Chaîne conservée intégralement, y compris les zéros finaux |
| `cost.currency` | Chaîne de trois lettres majuscules, code de devise fourni par le backend | Affichée après le montant, par exemple `0.00123000 USD` |

Tous les champs sont optionnels. Les entiers sûrs vont de 0 à 9007199254740991.
Les booléens, chaînes numériques pour les compteurs, valeurs négatives,
fractions de tokens et objets à la place d’une valeur sont rejetés champ par
champ ; les autres métriques valides restent affichées. `cost` nécessite **les
deux champs valides** : montant seul ou devise seule donne Non disponible.
Un montant JSON numérique est volontairement refusé : une chaîne est nécessaire
pour conserver la précision choisie par le backend. Le frontend ne lui ajoute
ni symbole monétaire supposé ni nombre de décimales par défaut.

Les métriques doivent concerner **la requête courante entière**, selon le
périmètre mesuré côté serveur, y compris les appels multiples et leurs tokens.
Le backend est responsable de leur cohérence et de la précision du coût.
Les durées individuelles Python/SQL restent dans la comparaison ; elles ne
sont jamais additionnées pour remplacer le temps total.

### Priorités et états

`request_info.status`, s’il est présent, est prioritaire. Sinon, le frontend lit
le `status` à la racine. En l’absence des deux, le verdict backend `concordance`
donne **Réponse vérifiée** et `divergence` donne **Réponse non validée**.
Un statut explicitement inconnu ou `null` reste Non disponible. Le frontend ne
déduit **jamais la confiance du verdict**, des résultats ou de la formulation
de la réponse : il lit seulement le niveau fourni par le backend. Les scores
numériques de confiance ne sont pas convertis en niveaux.

Les états ont des libellés et des couleurs distincts : réponse vérifiée (vert),
non validée (orange), demande de précision (bleu), refus de sécurité ou refus
sans motif spécifié (violet), erreur technique (rouge). Un refus, une précision
ou une erreur structurée empêche d’afficher une synthèse/comparaison validée,
même si un verdict contradictoire accompagne la réponse. Un refus explicite
ou une erreur structurée affiche aussi Refus ou Erreur dans la confiance, au
lieu de présenter une éventuelle confiance élevée contradictoire.
Le statut `unverified` empêche aussi une concordance contradictoire de valider la
synthèse ; les résultats individuels Python/SQL restent consultables.

Une erreur HTTP, JSON, réseau ou de protocole SSE est identifiée comme une
**erreur technique de la requête**, sans inventer de confiance ni de métriques.
Un code HTTP 403 seul n’est pas interprété comme un refus de sécurité ; ce motif
nécessite un statut explicite. Les métadonnées d’un refus/précision structurés
restent reconnues même avec un code HTTP non 2xx. Exemple :

```json
{
  "ok": false,
  "error": { "message": "Cette demande ne peut pas être traitée." },
  "request_info": {
    "status": "security_refusal",
    "metrics": { "model_calls": 1, "input_tokens": 40 },
    "cost": { "amount": "0.000080", "currency": "USD" }
  }
}
```

Les métadonnées d’erreur se placent à la racine, pas dans `error`. Pour une
enveloppe `{ "ok": true, "value": ... }`, `request_info` et
`total_duration_ms` sont lus dans `value`, ou sur l’enveloppe s’ils en sont absents.
Lors du parcours `/chat` puis détail, les champs à la racine du détail remplacent
ceux de `/chat` lorsqu’ils sont présents. Un `request_info` absent du détail
conserve celui de `/chat` ; présent, il le remplace **entièrement**, sans fusion
interne, y compris s’il vaut `null`. Si la lecture du détail échoue, les métriques
déjà reçues de `/chat` restent utilisables avec le diagnostic d’erreur.

Pour compatibilité, `total_duration_ms` à la racine est utilisé uniquement si
`request_info.metrics.total_duration_ms` est absent. Une valeur explicitement
`null` ou invalide dans ce dernier ne déclenche pas ce repli.

Le flux ne compte pas ses événements pour fabriquer des métriques. Seuls `final`
ou `error` les fournissent. Un `final` minimal avec `answer` reste compatible,
avec les champs Palier 5 Non disponible pour un ancien serveur. Le backend
actuel fournit explicitement `request_info.status` pour distinguer refus et
précision. Aucun examen du texte ne la remplace.

### Cycle de vie et sécurité du rendu

Une nouvelle question acceptée efface immédiatement les anciennes métriques,
le coût et la confiance, avant l’attente HTTP/SSE. Un import réussi les efface
aussi. Une annulation de lecture SSE laisse les valeurs finales indisponibles ;
elle ne simule ni arrêt du backend ni durée finale. Les contrôles running/stopped,
le journal et les opérations de test n’altèrent pas ces informations de requête.

Les fonctions centralisées dans `static/js/app.js` sont `validateRequestInfo`,
`requestValue`, `renderRequestInfo`, `renderMetrics`, `renderConfidence`,
`renderCost` et `resetRequestInfo`. Elles sont partagées avec le rendu SSE.
Les libellés/classes proviennent de listes fermées ; les champs backend utilisent
uniquement `textContent`. Les champs supplémentaires de `request_info` sont
ignorés : aucun affichage de JSON brut, de debug ou de prompt dans cette carte.

Le backend **doit exclure les secrets et prompts système avant toute transmission**,
y compris dans les textes publics `answer`, `message`, `error.message`, le journal
et la trace. `textContent` évite l’interprétation HTML, mais ne cache pas un secret
présent dans une phrase. En défense supplémentaire à la réception HTTP/SSE,
`publicBackendData` retire les champs nommés comme clés API, secrets, mots de passe,
autorisation, access/refresh tokens et prompts système, même imbriqués ; il masque
aussi les formats de clés `sk-…` et `Bearer …` reconnaissables. Les champs publics
input/output/total tokens sont conservés. Ce filtre ne peut pas identifier un
prompt système arbitraire envoyé à tort comme réponse publique : l’exclusion à
la source reste obligatoire. Aucune clé, aucun prompt ni configuration privée
n’est ajouté au frontend.

### Vérification

- `node --test tests/frontend.test.cjs` : contrat complet/partiel/absent/invalide,
  zéros, absence de calcul, précision du coût, tous les niveaux et états, priorités,
  enveloppes, HTTP non 2xx, SSE, effacement et contenu malveillant/secrets.
- `.venv/bin/python -m pytest -q tests/test_browser.py` : fixtures HTTP et SSE Palier 5,
  rendu mobile, absence d’exécution HTML et erreurs/refus ; parcours réels
  conservés pour imports, comparaison, trace, SSE, contrôle agent et opérations.

## Bonus +3 Palier 5 : coût basé sur la consommation Anthropic

`app/model_pricing.py` centralise les tarifs et `RequestUsage` agrège les
compteurs pendant **une seule requête utilisateur**. Aucun compteur ne provient
de la longueur du texte, d’un tokenizer local ou d’un événement SSE.

- `model_calls` augmente juste avant chaque invocation de
  `client.messages.create`, y compris si cet appel échoue. Le SDK conserve
  `max_retries=0` : aucun réessai implicite n’échappe au compteur.
- Dès le retour, `usage.input_tokens` et `usage.output_tokens` sont additionnés
  aux compteurs précédents, **avant** le contrôle d’annulation Palier 4. Le
  contenu métier n’est exploité qu’après ce contrôle.
- `tool_calls` augmente immédiatement avant l’exécution réelle de
  `verify_expenses`, même si l’outil échoue ou si un STOP survient pendant son
  exécution. Un événement `tool_call` suspendu avant l’exécution ne suffit pas.
- `calls = model_calls + tool_calls` ; les deux calculateurs, les lectures
  SQLite et les événements SSE ne sont pas comptés séparément.
- `input_tokens` représente la somme du champ Anthropic du même nom, donc
  l’entrée **standard, hors cache**. `total_tokens = input_tokens + output_tokens`
  suit ce contrat. Les tokens de cache restent dans des compteurs distincts ;
  ils sont inclus dans le coût, sans modifier cette définition du total.

### Tarifs, précision et cache

Tarifs standard Sonnet 5 vérifiés le 9 septembre 2026 dans la
[documentation Anthropic](https://platform.claude.com/docs/en/about-claude/pricing) :

| Catégorie | USD / million de tokens |
| --- | --- |
| Entrée standard | 2 |
| Sortie | 10 |
| Lecture de cache | 0.20 |
| Écriture cache 5 minutes | 2.50 |
| Écriture cache 1 heure | 4 |

Les modèles supplémentaires présents dans `dev` sont conservés dans la même
table `Decimal` : `claude-opus-5` (entrée 5, sortie 25, lecture cache 0.50,
écriture 5 min 6.25 et 1 h 10 USD/MTok) et `claude-haiku-4-5` (entrée 1,
sortie 5, lecture cache 0.10, écriture 5 min 1.25 et 1 h 2 USD/MTok).

Le calcul utilise exclusivement `Decimal`, y compris les constantes, les
multiplications, la division et le formatage final :

```text
coût USD = (input_tokens × 2 + output_tokens × 10
            + cache_read_input_tokens × 0.20
            + cache_creation_5m_input_tokens × 2.50
            + cache_creation_1h_input_tokens × 4) / 1000000
```

`amount` est une chaîne à huit décimales. Avec ces tarifs, cette précision
représente exactement les coûts par token, sans float intermédiaire. Pour
100 tokens d’entrée et 20 tokens de sortie sans cache : `0.00040000 USD`.
Les tarifs sont locaux : aucun téléchargement de prix pendant les requêtes.
Un `ANTHROPIC_MODEL` absent/vide utilise le modèle par défaut `claude-sonnet-5`.
Un autre identifiant non déclaré dans la table conserve les tokens réels mais
renvoie `cost: null`, sans appliquer le prix Sonnet à un modèle inconnu.

L’agent n’active pas actuellement `cache_control`. Si Anthropic fournit des
compteurs de cache, le backend expose aussi dans `metrics` :

- `cache_read_input_tokens` ;
- `cache_creation_5m_input_tokens`, issu de
  `usage.cache_creation.ephemeral_5m_input_tokens` ;
- `cache_creation_1h_input_tokens`, issu de
  `usage.cache_creation.ephemeral_1h_input_tokens` ;
- `cache_creation_input_tokens`, somme des deux durées connues.

Quand la ventilation est présente, le total de création Anthropic n’est jamais
facturé une seconde fois. Une ventilation partielle ou incohérente rend le coût
indisponible. Sans ventilation, le total de création est facturé au TTL Anthropic
par défaut de 5 minutes. Les compteurs optionnels de cache absents ou `null`
valent zéro dans les réponses d’usage sans cache. Le frontend actuel n’ajoute
pas de lignes de cache : il affiche le coût qui les prend déjà en compte.

### Erreurs, annulations et persistance

Chaque `final` ou `error` de l’agent possède un instantané public `request_info`.
Il accompagne `/chat`, les réponses sans outil (précision ou refus textuel), les
erreurs HTTP et les événements terminaux SSE. Aucune réponse Anthropic brute,
clé, en-tête d’authentification, prompt ou credential n’y est copié.

`usage_complete: true` signifie que les compteurs reçus permettent de calculer
le coût de toute l’exécution. Si un appel a été engagé sans réponse d’usage
exploitable (erreur réseau/API, usage absent ou invalide), ce drapeau vaut
`false` et `cost` vaut `null`. Les compteurs déjà reçus restent des sommes
**partielles connues** ; un compteur requis jamais reçu reste `null`, et n’est
pas remplacé par zéro. Le navigateur ignore ce drapeau supplémentaire mais
n’affiche aucun coût partiel comme coût final.

Avant tout appel (clé absente, question invalide, agent déjà arrêté), les
compteurs sont réellement zéro et le modèle supporté retourne `0.00000000 USD`.
Une erreur après réception d’un usage valide, dont un refus API avec
`stop_reason: "refusal"`, conserve le coût connu. Aucun motif de refus n’est
déduit du texte. Les refus applicatifs structurés utilisent un événement `final`
avec `security_refusal` ou `refused`, distinct de cet arrêt du protocole API.

Après un STOP, la génération invalide reste prioritaire : aucun résultat métier
issu de la réponse annulée n’est exploité. Les tokens déjà reçus et leur coût
restent disponibles dans l’erreur. STOP puis START ne réactive pas l’ancienne
exécution. Les erreurs lors de la persistance conservent aussi la consommation.

La colonne nullable `calculations.request_info_json` stocke l’instantané dans
la même transaction que le calcul. `init_db` migre automatiquement les anciennes
bases ; leurs anciennes lignes renvoient `request_info: null`, sans reconstitution.
`GET /calculations/{id}` relit cet instantané sans appel Claude ni recalcul du
coût. La réponse finale SSE réutilise le même détail persisté que le parcours
classique. La confiance et le verdict ne sont pas fabriqués à partir du coût.

### Exemple mesuré avec la vraie API

Validation navigateur du 9 septembre 2026, sur une base temporaire avec deux
dépenses de test et une question sur le total. Le parcours classique a réellement
renvoyé cet objet, affiché `0.00707200 USD`, et présenté la comparaison validée :

```json
{
  "request_info": {
    "metrics": {
      "calls": 3,
      "model_calls": 2,
      "tool_calls": 1,
      "input_tokens": 2821,
      "output_tokens": 143,
      "total_tokens": 2964,
      "cache_read_input_tokens": 0,
      "cache_creation_input_tokens": 0,
      "cache_creation_5m_input_tokens": 0,
      "cache_creation_1h_input_tokens": 0
    },
    "cost": {"amount": "0.00707200", "currency": "USD"},
    "usage_complete": true
  }
}
```

Une seconde requête réelle, en SSE, a affiché `0.00711200 USD` : 2821 tokens
input, 147 output, 2 appels modèle et 1 appel outil. Deux requêtes indépendantes
peuvent produire des sorties de longueurs différentes ; le test de parité
HTTP/SSE utilise des réponses API contrôlées identiques pour comparer les
métriques exactement. Le cache est testé avec une fixture du SDK, pas annoncé
comme exercé par ces deux requêtes réelles sans cache.

### Intégration du durcissement de dev

`POST /chat` et `POST /chat/stream` rejettent en HTTP 400 les questions vides,
mal typées, de plus de 1500 caractères après suppression des espaces aux
extrémités, ou contenant les caractères de contrôle interdits. Les retours à
la ligne et tabulations restent acceptés. Ces refus surviennent avant tout
appel Claude et conservent les compteurs de consommation à zéro prévus plus haut.

`request_info` constitue le contrat de consommation commun. Le format
intermédiaire `usage.cost_estimate_usd` de `dev` n’est pas produit en parallèle ;
le calcul `Decimal` existant remplace son calcul flottant. Une ancienne base de
`dev` peut conserver sa colonne `usage_json` : la migration ajoute
`request_info_json` sans supprimer ses données. Les anciens calculs sans
instantané `request_info` restent indisponibles pour le coût, sans conversion
rétroactive du coût flottant ni hypothèse sur un cache non enregistré.

La confiance est attribuée côté backend après un résultat de vérification.
Elle est réévaluée à la lecture selon les preuves disponibles ; le coût persisté
reste inchangé. Un STOP ou une erreur de stockage après calcul retire cette
confiance des réponses d’erreur tout en conservant la consommation connue.
