# Déploiement de démonstration sur Render

Le fichier `render.yaml` prépare un service Docker gratuit sur la branche `dev`.
Gunicorn sert Flask sur le port fourni par Render ; `/health` vérifie le démarrage.
La clé Anthropic n'est pas nécessaire pour obtenir une page publique et importer
un CSV. Elle est nécessaire pour utiliser les questions avec Claude réel.

## Première publication

1. Publier manuellement les changements du dépôt sur GitHub, branche `dev`, selon
   votre procédure Git. Render doit pouvoir lire `render.yaml`, `gunicorn.conf.py`,
   `Dockerfile` et `requirements.txt` mis à jour.
2. Ouvrir https://dashboard.render.com/ puis **New → Blueprint**.
3. Connecter GitHub si nécessaire et sélectionner
   `John-Natty/Holberton-school-Hackathon-le-Sosie`.
4. Sélectionner la branche **dev** et le fichier **render.yaml**. Vérifier que le
   service proposé est **Free**, puis créer le Blueprint.
5. Attendre l'état **Live**, puis ouvrir l'URL `https://…onrender.com` affichée par
   Render. Le nom exact est attribué à la création ; aucune URL n'est réservée
   par les fichiers locaux.
6. Vérifier la page d'accueil, puis `/health`, qui doit répondre
   `{"status":"ok"}`. Importer uniquement le CSV fictif du README.

Si le service existe déjà, ne pas en créer un second : régler sa branche sur
`dev`, son runtime sur Docker et son contrôle de santé sur `/health`, puis utiliser
**Manual Deploy → Deploy latest commit** après publication des changements.

Pour les questions réelles : dans **Environment**, ajouter `ANTHROPIC_API_KEY`
avec une clé disposant de crédits, puis enregistrer et redéployer. Ne pas mettre
la clé dans `render.yaml`, Git, JavaScript ou une capture d'écran.
`ANTHROPIC_MODEL` peut être adapté au modèle accessible sur le compte.

## Mémoire des contrôles locaux

Le filtre de langue utilise `langdetect` et ses petits profils statistiques ; la
modération utilise des règles Python. Aucun runtime ONNX, tokenizer neuronal ni
poids mDeBERTa n'est installé dans la nouvelle image. Le téléchargement de modèle
pendant le build a été supprimé. Gunicorn garde `workers = 1`, `threads = 4` et
le plan Render reste `free`.

L'ancienne modération créait, lors de son premier usage, une `InferenceSession`
ONNX pour environ 339 Mo de poids, plus le tokenizer et les buffers d'inférence.
Lingua chargeait en parallèle ses profils multilingues. C'est cette allocation
qui rendait la couche locale trop lourde pour le service. Le fournisseur ONNX
était déjà limité à `CPUExecutionProvider` ; un warning de découverte GPU ne
prouve pas une utilisation du GPU et ne mesure pas la consommation mémoire.

Après reconstruction avec les nouvelles dépendances, le processus ne charge plus
ces composants. Le gain attendu est de plusieurs centaines de Mo ; le RSS réel
et le comportement sous charge restent à vérifier sur le service. Aucun test ni
redéploiement Render n'a été exécuté pour ce correctif. Les règles légères ont une
couverture linguistique et sémantique limitée, détaillée dans le README.

## Limites de cette publication anticipée

- Le palier actuel n'a ni comptes utilisateurs ni séparation des jeux de données.
  Tous les visiteurs peuvent consulter les dépenses et en importer. Utiliser
  exclusivement des dépenses fictives.
- Si une clé Claude est configurée, les questions de tous les visiteurs utilisent
  ses crédits. Pour une première URL publique sans usage API, laisser la clé absente.
- L'offre gratuite utilise un disque éphémère : la base peut disparaître lors
  d'un redémarrage, d'un redéploiement ou d'une mise en veille. Le volume de
  `compose.yaml` est uniquement local et n'est pas repris par Render.
- Le service gratuit se met en veille après 15 minutes sans trafic ; son premier
  réveil peut prendre environ une minute.
- La conservation durable de SQLite demande un service payant et un disque
  persistant, à configurer séparément. Ce Blueprint ne crée aucun disque payant.
- Les déploiements automatiques sont désactivés : après les premiers changements,
  utiliser **Manual Deploy** pour publier une nouvelle révision.

Sources : [Docker sur Render](https://render.com/docs/docker),
[Blueprints](https://render.com/docs/blueprint-spec),
[offre gratuite](https://render.com/docs/free).
