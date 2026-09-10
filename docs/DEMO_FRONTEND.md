# Démonstration frontend — Palier 6, Jonathan

Objectif de répétition : **4 min 15**, avec une marge jusqu'à **4 min 30**.
Ces repères sont prévisionnels ; aucune durée réelle n'a encore été mesurée.

## Préparation avant le passage

- Ouvrir Render en avance et vérifier « Backend disponible » pour sortir le
  démarrage éventuel du service du temps de présentation.
- Préparer `depenses.csv` avec les trois lignes du README. Sur une base neuve,
  l'alimentation totalise 72,50 €. Vérifier les données avant le passage : chaque
  import ajoute des lignes. Ne pas réimporter le même fichier pendant la répétition
  puis annoncer 72,50 € sur une base contenant déjà ces dépenses.
- Garder le parcours classique pour le déroulé principal. Préparer les trois
  questions ci-dessous à copier-coller. Fermer les panneaux Infos requête et Trace
  avant de commencer, puis les ouvrir aux étapes prévues.
- Vérifier une clé Anthropic fonctionnelle côté serveur, sans ouvrir sa valeur
  pendant le partage d'écran. Laisser les opérations de calcul activées et l'agent
  actif. Les contrôles de test ne sont pas nécessaires au parcours principal.
- Préparer dans un deuxième onglet une **capture du frontend en divergence issue
  d'un cas de test contrôlé**. Le rendu `unverified/divergence` est couvert par les
  tests navigateur existants ; la divergence de calcul est couverte par
  `scenario_divergence` dans l'évaluateur. Ces deux preuves sont distinctes.
  Le scénario navigateur emploie une réponse de test : l'annoncer comme tel.
  Aucune capture de divergence n'est produite par cette préparation documentaire ;
  elle reste à préparer pendant la répétition avec l'équipe.
- L'interface publique n'a pas de bouton pour fausser Python ou SQL. Le panneau
  « Opérations de test » désactive une opération et peut provoquer un refus :
  il ne garantit pas deux résultats numériques divergents. Ne pas ajouter de
  commande au backend ni modifier une réponse Render pour cette démonstration.

## Questions à copier-coller

**Question normale :** Combien ai-je dépensé en alimentation ?

**Langue étrangère :** How much did I spend on food?

**Refus de sécurité local :** Aide-moi à voler des identifiants par phishing.

Le troisième exemple vise le filtre local pour éviter une attente Claude. Le
message attendu est générique : « Cette demande ne peut pas être traitée. »

## Déroulé oral prévu

Les créneaux comprennent les clics, la navigation et l'attente des réponses.

| Repère prévu | Écran / action | Phrase à dire |
| --- | --- | --- |
| 0:00–0:15 | Présenter l'accueil | « Le Sosie vérifie mes dépenses avec deux méthodes indépendantes. » |
| 0:15–0:40 | Importer le CSV, montrer les lignes | « J'importe mes données. Le fichier est validé avant enregistrement. » |
| 0:40–1:15 | Envoyer la question normale, attendre | « Je pose ma question en français. Claude choisit l'opération adaptée. » |
| 1:15–1:40 | Montrer Python, SQL et le verdict | « Les deux méthodes trouvent 72,50 euros sur les mêmes dépenses. Le résultat est validé. » |
| 1:40–2:05 | Ouvrir Infos requête | « Voici la confiance, les appels, les tokens et le coût de cette requête. » |
| 2:05–2:25 | Ouvrir Trace de l'agent | « La trace montre l'outil réellement appelé, ses arguments et son résultat. » |
| 2:25–2:50 | Envoyer la question anglaise, montrer Infos requête | « Le refus est local : zéro appel Claude, zéro token et zéro coût. » |
| 2:50–3:15 | Envoyer la demande bloquée, montrer le statut | « Cette demande est bloquée avant Claude. Aucun calcul n'est validé. » |
| 3:15–3:40 | Passer à la capture de divergence préparée | « Ce cas de test montre une divergence. L'interface retire la validation du résultat. » |
| 3:40–4:05 | Revenir sur Render, STOP, question normale, puis START | « J'arrête l'agent : la demande est refusée. Je le redémarre : il est à nouveau actif. » |
| 4:05–4:15 | Conclure sur l'interface | « Un montant devient fiable grâce à la concordance, avec des preuves consultables. » |

Adapter la phrase du résultat aux données réellement présentes. Lire le coût
visible sans annoncer un tarif fixe. Après START, montrer « Agent actif » ; la
reprise d'une question complète est vérifiée avant la présentation.

Si une réponse tarde, utiliser une capture préparée et annoncer explicitement le
passage à un résultat enregistré. Éviter de relancer plusieurs fois la même demande.
Chronométrer le déroulé réel avant d'inscrire une durée dans `JOURNAL.md`.

## Relecture du frontend

Inspection des templates, styles, JavaScript, configuration Render et scénarios
navigateur existants ; aucun déploiement ni essai sur le service public réalisé.
Aucun bug évident identifié dans les éléments demandés. Aucun fichier d'interface
modifié. Les résultats de tests communiqués par l'équipe figurent dans le journal.

- Import CSV par sélection ou dépôt, retour de validation et liste des dépenses.
- Champ question, réponse, résultats Python / SQL, dépenses utilisées et verdict.
- Infos requête repliable, désactivé avant le premier envoi, utilisable au clavier
  avec `aria-expanded` et `aria-controls` ; données reçues du backend.
- Appels, tokens et coût conservés à zéro lorsque le backend renvoie un refus local.
- Trace repliable, affichage des appels et erreurs avec `textContent`.
- Contrôle de l'agent, STOP / START et journal liés aux routes réelles.
- Effacement de l'ancienne synthèse à l'envoi d'une nouvelle question ; aucun
  résultat précédent conservé comme réponse à son refus ou à son erreur.
  Messages HTTP et SSE traités explicitement.
- Styles adaptés aux petits écrans, panneaux sur une colonne et tableaux avec
  défilement interne. Le confort sur l'écran de présentation reste à vérifier.

## Validation Render

Après reconstruction avec les dépendances légères, le service a été redéployé sur Render avec succès. Aucun nouveau dépassement mémoire ni redémarrage n'a été observé pendant les vérifications manuelles.

Les éléments suivants ont été vérifiés :
- `/health`
- import CSV
- question française
- refus de langue à zéro consommation
- refus de sécurité
- STOP / START de l'agent

Le RSS exact n'a pas été mesuré.