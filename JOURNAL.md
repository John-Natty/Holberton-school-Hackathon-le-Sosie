# Journal — Le Sosie

## Palier 1 — Cadrage

- Définition du besoin : vérifier les dépenses à partir des données fournies.
- Spécification, menaces, contrats des outils et répartition du travail.
- Principe retenu : comparer deux calculateurs indépendants, sans arbitrage
  inventé en cas de désaccord.

## Palier 2 — Socle

- Application Flask, SQLite et import CSV validé avant insertion atomique.
- Calculs Python et SQL comparés sur les montants et les dépenses utilisées.
- Première interface : import, dépenses, question, réponse et comparaison.
- Lancement Docker et publication de démonstration sur Render avec Gunicorn.

## Palier 3 — Boucle de l'agent

- Claude appelle réellement `verify_expenses` ; le serveur valide les arguments.
- Trace des appels, arguments, succès et erreurs reçus du backend.
- Parcours HTTP et exécution en direct SSE : même logique de vérification.

## Palier 4 — Contrôle

- STOP / START depuis l'interface, état réel et journal d'exécution horodaté.
- Un STOP invalide l'exécution en cours ; un START ne la réactive pas.
- Ajout de l'évaluateur automatisé, aujourd'hui composé de 17 scénarios.

## Palier 5 — Durcissement et transparence

- Validation des entrées, refus de sécurité et rejet des sorties Claude non
  conformes au contrat structuré, sans leur attribuer de résultat fiable.
- Langue contrôlée localement par Unicode et `langdetect`, avant Claude.
- Modération par règles Python légères, avant Claude et avant insertion CSV.
  Les refus locaux consomment zéro appel, zéro token Anthropic et zéro coût.
- Panneau repliable « Infos requête » : état, confiance, durée, appels, tokens
  et coût fournis par le backend ; aucune estimation inventée par l'interface.
- Évaluateur adapté aux issues sûres de Claude : refus direct ou outils échoués
  avant calcul ; pour l'injection SQL, l'erreur précise de contrat est admise.
  Un outil réussi, un calcul lancé ou une modification des données restent refusés
  dans ces scénarios hostiles.

## Palier 6 — Livraison, partie Jonathan

- Journal raccourci et README actualisé.
- Frontend relu : import, réponse, comparaison, métadonnées, trace et contrôle
  de l'agent. Aucun bug évident relevé à la lecture ; interface conservée.
- Checklist Render et déroulé oral préparés dans `docs/DEMO_FRONTEND.md`.
- Vérification manuelle sur Render et répétition chronométrée à réaliser.
  Aucune durée réelle de démonstration n'est encore consignée.
- Démonstration finale répétée en conditions réelles.
- Durée mesurée : environ 4 min 20 s.
- Parcours complet terminé dans la limite des 5 minutes.

## Dernière validation communiquée par l'équipe

- **363 tests Python réussis.**
- **34 tests frontend réussis.**
- **7 tests navigateur réussis.**
- **Évaluateur avec Claude réel : 17/17**, obtenu lors de plusieurs exécutions.

Ces résultats sont ceux transmis pour la livraison ; les suites n'ont pas été
relancées pendant ce nettoyage documentaire.

## Secret compromis

Toute clé exposée dans Git, les logs ou une démonstration est considérée comme
compromise : révocation chez le fournisseur, remplacement, puis vérification et
nettoyage des emplacements concernés. Supprimer la clé du dernier commit ne
suffit pas : elle peut déjà avoir été copiée, sa rotation reste obligatoire.
La nouvelle valeur reste côté serveur et n'est jamais consignée ici.

## Dette technique assumée

- La modération par règles Python est plus légère pour Render, mais moins
  performante sur certaines paraphrases qu'un modèle neuronal. Sa couverture
  linguistique est limitée ; des faux positifs et faux négatifs restent possibles.
- La démonstration Render utilise des données fictives partagées et une base
  SQLite éphémère. L'isolation des utilisateurs et la persistance durable restent
  hors du périmètre livré.
- Claude reste stochastique : une sortie non conforme est rejetée proprement.
  La concordance Python / SQL reste nécessaire pour considérer un montant fiable.
