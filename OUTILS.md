# OUTILS : Le Sosie

## Objectif

Ce document décrit les outils prévus pour le palier 1 du Sosie.

Les outils permettent de calculer et de vérifier les dépenses enregistrées dans l'application.

Les règles définies dans `SPEC.md` et `MENACES.md` s'appliquent à tous les outils.

## Types communs

Toutes les dépenses utilisées par les outils sont déjà validées et normalisées par l'application.

```text
ExpenseId = entier >= 1

DateISO = chaîne au format YYYY-MM-DD représentant une date valide

Operation =
    "total"
    | "total_by_category"
    | "total_by_period"

CalculationRequest = {
    operation: Operation,
    category: chaîne | null,
    start_date: DateISO | null,
    end_date: DateISO | null
}

CalculationResult = {
    result_cents: entier,
    expense_ids: liste[ExpenseId] triée par ordre croissant,
    duration_ms: nombre
}

Expense = {
    id: ExpenseId,
    date: DateISO,
    description: chaîne,
    category: chaîne,
    amount_cents: entier,
    source_type: chaîne
}
ToolError = {
    code: chaîne,
    message: chaîne
}

ToolResult[T] =
    { ok: true, value: T }
    | { ok: false, error: ToolError }
```

### Règles du contrat

Pour `total` :

```text
category = null
start_date = null
end_date = null
```

Pour `total_by_category` :

```text
category = catégorie demandée
start_date = null
end_date = null
```

Pour `total_by_period` :

```text
category = null
start_date = date de début
end_date = date de fin
```

La date de début doit être inférieure ou égale à la date de fin.

Les propriétés ou opérations inconnues doivent être refusées.

## Liste des outils

| Nom | Signature typée complète | Rôle | Effet de bord |
| --- | --- | --- | --- |
| `calculate_python` | `calculate_python(request: CalculationRequest) -> ToolResult[CalculationResult]` | Réalise le filtrage et le calcul avec Python à partir des dépenses normalisées. | Non |
| `calculate_sql` | `calculate_sql(request: CalculationRequest) -> ToolResult[CalculationResult]` | Réalise le même calcul avec des requêtes SQLite prédéfinies et paramétrées. | Non |
| `get_expenses` | `get_expenses(expense_ids: list[ExpenseId]) -> ToolResult[list[Expense]]` | Retrouve les dépenses utilisées par un calcul afin de permettre leur vérification. | Non |

## calculate_python

Signature :

```text
calculate_python(
    request: CalculationRequest
) -> ToolResult[CalculationResult]
```

Le calculateur Python :

- récupère les dépenses normalisées ;
- applique lui-même les filtres demandés ;
- sélectionne les dépenses concernées ;
- additionne les montants en centimes ;
- retourne le résultat ;
- retourne les identifiants des dépenses utilisées ;
- mesure sa durée d'exécution.

Il ne reçoit jamais le résultat SQL.

Exemple :

```text
Entrée :

{
    operation: "total_by_category",
    category: "Alimentation",
    start_date: null,
    end_date: null
}

Sortie :

{
    ok: true,
    value: {
        result_cents: 7250,
        expense_ids: [1, 4, 7],
        duration_ms: 3.4
    }
}
```

## calculate_sql

Signature :

```text
calculate_sql(
    request: CalculationRequest
) -> ToolResult[CalculationResult]
```

Le calculateur SQL :

- travaille sur les mêmes dépenses normalisées ;
- utilise uniquement des requêtes prédéfinies ;
- utilise des paramètres SQL ;
- sélectionne lui-même les dépenses concernées ;
- effectue le calcul avec SQLite ;
- retourne le résultat ;
- retourne les identifiants des dépenses utilisées ;
- mesure sa durée d'exécution.

Il ne reçoit jamais le résultat Python.

Le texte fourni par l'utilisateur ou par le LLM ne doit jamais être exécuté directement comme une requête SQL.

## get_expenses

Signature :

```text
get_expenses(
    expense_ids: list[ExpenseId]
) -> ToolResult[list[Expense]]
```

Cet outil permet de retrouver les dépenses ayant participé à un calcul.

Exemple :

```text
Entrée :

[1, 4, 7]
```

Sortie :

```text
{
    ok: true,
    value: [
        {
            id: 1,
            date: "2026-09-01",
            description: "Carrefour",
            category: "Alimentation",
            amount_cents: 4250,
            source_type: "csv"
        },
        {
            id: 4,
            date: "2026-09-03",
            description: "Boulangerie",
            category: "Alimentation",
            amount_cents: 1200,
            source_type: "manual"
        },
        {
            id: 7,
            date: "2026-09-05",
            description: "Restaurant",
            category: "Alimentation",
            amount_cents: 1800,
            source_type: "image"
        }
    ]
}
```

Cet outil est en lecture seule.

## Rôle du LLM

Le LLM ne réalise aucun calcul financier lui-même.

Son rôle est de comprendre la question de l'utilisateur et de produire une opération structurée.

Exemple :

```text
Question :

Combien ai-je dépensé en alimentation ?
```

devient :

```text
{
    operation: "total_by_category",
    category: "Alimentation",
    start_date: null,
    end_date: null
}
```

Si une information nécessaire manque, le système doit demander une précision.

Exemple :

```text
Combien ai-je dépensé récemment ?
```

Le système doit demander quelle période l'utilisateur souhaite analyser.

## Exécution des deux calculateurs

Le LLM ne choisit pas s'il faut utiliser Python ou SQL.

Une fois la demande validée, le backend impose l'exécution des deux calculateurs avec exactement le même contrat.

```text
                    CalculationRequest
                          |
                 +--------+--------+
                 |                 |
                 v                 v
        calculate_python     calculate_sql
                 |                 |
                 v                 v
          résultat Python    résultat SQL
                 |                 |
                 +--------+--------+
                          |
                          v
                     Comparateur
```

Les deux calculateurs doivent rester indépendants.

Ils peuvent partager :

- les dépenses validées ;
- le même contrat de calcul.

Ils ne doivent pas partager :

- leur logique de filtrage ;
- leur résultat ;
- leur sélection de dépenses ;
- leurs résultats intermédiaires.

## Comparaison

La comparaison est réalisée par l'application et non par le LLM.

Le comparateur vérifie au minimum :

```text
result_cents Python == result_cents SQL

expense_ids Python == expense_ids SQL
```

Si les montants et les dépenses sont identiques, le résultat est considéré comme concordant.

Si les montants sont différents, il y a divergence.

Si les montants sont identiques mais que les `expense_ids` sont différents, il y a également divergence.

Le LLM ne peut pas transformer une divergence en concordance.

Les deux calculateurs doivent retourner les `expense_ids` triés par ordre croissant afin de garantir une comparaison stable.

## Fonctions qui ne sont pas des outils de calcul

Certaines fonctions appartiennent à l'application mais ne font pas partie des outils de calcul Python et SQL.

Par exemple :

- ajout manuel d'une dépense ;
- ajout de plusieurs dépenses ;
- import CSV ;
- envoi d'une image ;
- extraction des informations d'un fichier ;
- validation des données ;
- normalisation ;
- enregistrement dans SQLite ;
- comparaison des résultats.

Ces fonctions préparent ou gèrent les données.

Python et SQL interviennent uniquement une fois les dépenses validées et normalisées.

## Gestion des erreurs

Un outil doit retourner une erreur si :

- l'opération est inconnue ;
- les paramètres sont invalides ;
- une date est invalide ;
- une catégorie obligatoire est absente ;
- la base de données est indisponible ;
- le calcul échoue.

Une erreur ne doit jamais être transformée en résultat numérique valide.

Si Python ou SQL échoue, Le Sosie ne doit pas annoncer que le calcul est concordant.

## Effets de bord

Les trois outils du palier 1 sont en lecture seule.

| Outil | Effet de bord |
| --- | --- |
| `calculate_python` | Non |
| `calculate_sql` | Non |
| `get_expenses` | Non |

Ils ne peuvent pas :

- ajouter une dépense ;
- modifier une dépense ;
- supprimer une dépense ;
- modifier le résultat de l'autre calculateur.

Les écritures nécessaires à l'ajout ou à l'import de dépenses sont gérées séparément par l'application.
