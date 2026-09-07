# SPEC — Le Sosie

## Le problème (5 lignes)

Lorsqu'un utilisateur demande à une IA d'analyser ses dépenses, une réponse chiffrée peut sembler crédible tout en étant fausse ou impossible à vérifier. Le Sosie permet à l'utilisateur de fournir ses propres dépenses puis de poser une question en langage naturel, par exemple « Combien ai-je dépensé en alimentation ce mois-ci ? ». La demande est transformée en une opération structurée puis envoyée à **deux méthodes de calcul indépendantes**, une en Python et une en SQL, travaillant sur les mêmes données. Les deux résultats sont ensuite comparés, avec les dépenses ayant participé au calcul. Le système affiche le résultat lorsque les deux méthodes concordent et signale clairement toute divergence au lieu de choisir arbitrairement une réponse.

## User stories (3 max)

1. **En tant qu'utilisateur**, je veux fournir mes dépenses afin que Le Sosie puisse travailler uniquement à partir de mes propres données.

2. **En tant qu'utilisateur**, je veux poser une question sur mes dépenses en langage naturel afin d'obtenir un calcul réalisé indépendamment par Python et SQL.

3. **En tant qu'utilisateur**, je veux voir les résultats des deux méthodes et les dépenses utilisées afin de comprendre si les deux calculs concordent et de pouvoir vérifier la réponse.

## Hors scope (10 items)

- Pas de connexion bancaire, d'Open Banking ou d'accès à un compte bancaire : toutes les données sont fournies directement par l'utilisateur.
- Pas de récupération automatique de transactions depuis une banque ou un service financier externe.
- Pas d'import PDF, d'image ou d'OCR : le format d'import du MVP est le CSV.
- Pas d'import Excel ou d'adaptation automatique de tous les formats de CSV bancaires existants : l'application utilise un format CSV défini par le projet.
- Pas de prédiction des dépenses futures, de conseil financier ou de recommandation d'investissement.
- Pas de conversion entre plusieurs devises : les montants du MVP sont exprimés en euros.
- Pas de catégorisation automatique des dépenses par IA : la catégorie est fournie dans les données utilisateur.
- Pas de génération libre de requêtes SQL par le LLM : seules des opérations définies et des requêtes SQL paramétrées sont exécutées.
- Pas de gestion avancée des comptes, organisations, rôles ou budgets partagés dans le MVP.
- Pas de troisième moteur de calcul chargé de déterminer systématiquement lequel de Python ou SQL a raison : en cas de divergence impossible à expliquer avec les données disponibles, Le Sosie indique qu'il ne peut pas valider le résultat.

## Format des données

Le format CSV prévu est :

```csv
date,description,categorie,montant
2026-09-01,Carrefour,Alimentation,42.50
2026-09-02,Essence,Transport,65.00
2026-09-03,Netflix,Abonnements,19.99
```

Règles principales :

- encodage UTF-8 ;
- séparateur `,` ;
- une ligne représente une dépense ;
- date au format `YYYY-MM-DD` ;
- description obligatoire ;
- catégorie obligatoire ;
- montant en euros ;
- montant stocké en centimes entiers après validation ;
- aucune ligne invalide ne doit être utilisée silencieusement dans un calcul.

Chaque dépense validée reçoit un identifiant permettant de retrouver les données ayant participé à un résultat.

## Schéma d'architecture

```mermaid
flowchart LR
    U[Utilisateur] -->|CSV + question en langage naturel| FRONT[Frontend HTML/CSS/JS]

    FRONT -->|import CSV| API[API Flask]
    API -->|validation et normalisation| DB[(SQLite)]

    FRONT -->|POST /chat| API
    API -->|question + opérations disponibles| AGENT[LLM]

    AGENT -->|requête structurée| API

    API -->|même contrat| PY[Calculateur Python]
    API -->|même contrat| SQL[Calculateur SQL]

    PY -->|lecture des dépenses| DB
    SQL -->|requêtes paramétrées| DB

    PY -->|résultat + expense_ids| COMP[Comparateur]
    SQL -->|résultat + expense_ids| COMP

    COMP -->|concordance ou divergence| API

    API -->|réponse + détails des deux calculs| FRONT
```

- **Front** : permet d'importer les dépenses, poser une question et consulter la réponse ainsi que les résultats Python et SQL.
- **Back** : valide les données, orchestre le LLM, lance les deux méthodes de calcul et applique les règles de comparaison.
- **Agent** : comprend la demande en langage naturel et la transforme en une opération structurée parmi celles autorisées. Il ne calcule pas lui-même le résultat final.
- **Calculateur Python** : filtre et additionne les dépenses avec du code Python.
- **Calculateur SQL** : réalise le même calcul avec des requêtes SQL prédéfinies et paramétrées.
- **Comparateur** : compare les valeurs retournées et les dépenses ayant participé au calcul.
- **Stockage** : SQLite contient les dépenses validées et les informations nécessaires pour les retrouver.
- **Isolation** : les deux calculateurs travaillent à partir des mêmes données mais réalisent leur calcul indépendamment. Aucun calculateur ne reçoit le résultat de l'autre.

## Opérations prévues

Le périmètre initial comporte trois opérations.

### Total des dépenses

Exemple :

> Combien ai-je dépensé au total ?

Contrat :

```text
operation: total
```

### Total par catégorie

Exemple :

> Combien ai-je dépensé en alimentation ?

Contrat :

```text
operation: total_by_category
category: Alimentation
```

### Total sur une période

Exemple :

> Combien ai-je dépensé entre le 1er et le 7 septembre ?

Contrat :

```text
operation: total_by_period
start_date: 2026-09-01
end_date: 2026-09-07
```

Une demande ambiguë doit entraîner une demande de précision.

Exemple :

> Combien ai-je dépensé récemment ?

Le système ne choisit pas lui-même ce que signifie « récemment ».

## Endpoints REST prévus

- `POST /imports` : importer et valider un fichier CSV.
- `GET /expenses` : consulter les dépenses du jeu de données courant.
- `POST /chat` : poser une question en langage naturel.
- `GET /calculations/{calculation_id}` : consulter le détail d'un calcul.
- `GET /health` : vérifier l'état de l'application.

Ces endpoints représentent le besoin actuel du palier 1 et pourront être adaptés pendant l'implémentation si nécessaire.

## Outils de l'agent

| Nom | Signature | Effet de bord |
| --- | --- | --- |
| `calculate_python` | `calculate_python(operation: str, category: str \| null, start_date: date \| null, end_date: date \| null) -> CalculationResult` | Non : lecture des dépenses puis calcul en Python |
| `calculate_sql` | `calculate_sql(operation: str, category: str \| null, start_date: date \| null, end_date: date \| null) -> CalculationResult` | Non : lecture des dépenses via une requête SQL paramétrée |
| `get_expenses` | `get_expenses(expense_ids: list[int]) -> list[Expense]` | Non : permet de retrouver les dépenses utilisées comme preuves |

Les deux calculateurs reçoivent exactement le même contrat.

Un `CalculationResult` contient au minimum :

```text
result_cents
expense_ids
duration_ms
```

Exemple :

```text
result_cents: 7250
expense_ids: [1, 4, 7]
duration_ms: 3.4
```

Le LLM ne peut pas modifier directement le résultat retourné par Python ou SQL.

## Comparaison des deux Sosies

### Concordance

Exemple :

```text
Python : 72.50 €
SQL    : 72.50 €

Python expense_ids : [1, 4, 7]
SQL expense_ids    : [1, 4, 7]
```

Le résultat peut être validé.

Réponse :

> Vous avez dépensé 72,50 € en alimentation. Les calculs Python et SQL concordent.

### Même montant mais données différentes

Exemple :

```text
Python : 72.50 €
SQL    : 72.50 €

Python expense_ids : [1, 4, 7]
SQL expense_ids    : [2, 5]
```

Les montants sont identiques mais les preuves ne le sont pas.

Le système considère cela comme une divergence.

### Montants différents

Exemple :

```text
Python : 72.50 €
SQL    : 79.50 €
```

Le Sosie ne choisit pas arbitrairement l'un des deux résultats.

Il affiche les deux réponses et les dépenses utilisées par chaque méthode.

Si les données disponibles ne permettent pas d'expliquer complètement l'écart, aucune réponse n'est présentée comme validée.

## Indépendance des calculs

Le calculateur Python doit :

- récupérer les dépenses ;
- réaliser son propre filtrage ;
- réaliser son propre regroupement ;
- effectuer son propre cumul.

Le calculateur SQL doit :

- utiliser ses propres conditions SQL ;
- utiliser des requêtes paramétrées ;
- effectuer les opérations avec SQL.

Aucun des deux calculateurs ne doit :

- recevoir le résultat de l'autre ;
- réutiliser la sélection de lignes produite par l'autre ;
- modifier son résultat pour le faire correspondre à l'autre.

La validation et la normalisation du CSV restent toutefois communes aux deux calculateurs.

Le Sosie vérifie donc principalement **deux méthodes de calcul indépendantes sur une même source de données**, et non deux chaînes complètement indépendantes depuis l'import jusqu'au résultat.

## Mesure du coût

Pour chaque calcul, Le Sosie mesure :

```text
durée Python
durée SQL
durée totale
```

Ces informations permettent de montrer le coût de la double exécution pendant la démonstration.

Les deux calculs peuvent être lancés en parallèle afin d'éviter que leur durée totale corresponde simplement à l'addition des deux temps d'exécution.

## Happy path de la démo finale (6 étapes)

1. L'utilisateur importe un CSV contenant plusieurs dépenses d'alimentation, de transport, de loisirs et d'abonnements.
2. L'application valide le fichier et affiche les dépenses enregistrées.
3. L'utilisateur demande : *« Combien ai-je dépensé en alimentation ? »*
4. L'agent transforme la question en une requête structurée `total_by_category` avec la catégorie `Alimentation`, puis les calculateurs Python et SQL sont lancés avec exactement les mêmes paramètres.
5. Les deux calculateurs retournent `72,50 €` avec les mêmes identifiants de dépenses ; le comparateur confirme la concordance.
6. L'interface affiche la réponse finale, les résultats Python et SQL, les dépenses ayant servi au calcul et la durée de chaque méthode.

## Répartition du travail

- **Noham** : backend, compréhension de la question, orchestration des deux calculateurs et logique de comparaison.
- **Jonathan** : frontend, import et affichage des dépenses, intégration des résultats et détails de comparaison.
- **En commun** : `SPEC.md`, modèle de données, tests de concordance/divergence, architecture et script de démonstration.
