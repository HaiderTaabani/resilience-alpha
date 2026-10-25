# Partie IA / Data : détection d'anomalies et assistant opérateur

*Contribution : le détecteur ML et le service rag-assistant ont été développés par Ismael ; le PC IA (Ollama, réseau, pare-feu, mesures) est tenu par Haider. Les paramètres ci-dessous sont ceux du dépôt au commit `002d6de`.*

## 1. Périmètre et principe

Deux composants d'IA, avec un partage des rôles volontairement strict :

| Composant | Rôle | Peut agir sur le système ? |
|---|---|---|
| Détecteur d'anomalies (Isolation Forest + règles) | Repère un comportement anormal et envoie un incident à la remédiation | Non : il alerte seulement |
| Assistant RAG (Ollama + LangChain) | Explique aux opérateurs, à partir de la documentation | **Non, aucun accès au système** |
| Moteur de remédiation (automate) | Répare et vérifie la reprise | Oui, c'est le seul |

Aucune donnée réelle n'est utilisée, et aucune donnée ne quitte le réseau du groupe : le modèle de langage tourne en local sur le PC IA.

## 2. Détection d'anomalies

### Données et préparation
- Source : métriques Prometheus du service d'authentification, relevées toutes les **5 secondes** (fenêtre de calcul : 10 s).
- Observations (vecteur de 4 mesures) : débit de requêtes, latence moyenne, taux d'erreurs 5xx, taux d'échecs de connexion par seconde.
- Trafic normal mesuré en laboratoire : environ 0,3 requête/s, 0 échec de connexion/s, latence p95 d'environ 44 ms.
- Apprentissage : **12 fenêtres normales (environ 1 minute)**, puis ré-entraînement toutes les 60 fenêtres sur une baseline glissante de 200 observations au maximum.

### Modèle
- **Isolation Forest** (scikit-learn) : 100 arbres, `contamination = 0,02`, graine fixée (42).
- Pourquoi ce choix : approche **non supervisée** (nous n'avons pas de données d'attaque étiquetées), légère, rapide à entraîner, et elle fournit un **score** interprétable.

### Décision : le modèle ne décide jamais seul
1. **Panne franche** : cible injoignable (`up = 0`) sur 2 fenêtres consécutives, sans passer par le modèle.
2. **Signatures déterministes**, immédiates et indépendantes du modèle : au moins 2 échecs de connexion/s (credential stuffing) ou 8 requêtes/s (flood).
3. **Anomalie ML confirmée** seulement si le modèle la signale sur **3 fenêtres consécutives ET** qu'un signal concret la corrobore (erreurs 5xx, au moins 1 échec de connexion/s, ou latence p95 d'au moins 1 000 ms).
4. Après un incident, **45 secondes** de pause avant le suivant.

Les mesures qui déclenchent une signature franche **n'alimentent jamais la baseline** du modèle : cela limite le risque d'« empoisonnement » (apprendre l'attaque comme du trafic normal).

### Limites constatées
- **Faux positifs** : avec `contamination = 0,1`, le modèle déclenchait à tort sur des pics isolés (bcrypt fait monter la latence jusqu'à environ 480 ms en usage légitime). Nous l'avons ramené à 0,02 et ajouté l'exigence d'un signal concret.
- **Baseline très courte** (environ 1 minute) et trafic de laboratoire très faible : le modèle est sensible, d'où les règles à seuil en complément.
- Une attaque très lente (« low and slow ») pourrait passer sous les seuils.
- Les seuils fixes (2 échecs/s, 8 requêtes/s) sont calés sur notre trafic de labo ; ils ne seraient pas transposables tels quels en production.

### Résultats mesurés
| Mesure | Valeur |
|---|---|
| Reprise après panne franche (service arrêté) | **13 s** (mesure de l'équipe) |

Le délai de détection d'un flood ou d'un credential stuffing et le taux de faux positifs n'ont pas fait l'objet d'une mesure chiffrée systématique : ils s'observent en direct sur le dashboard (frise de reprise et fil d'événements). C'est une limite que nous assumons (voir ci-dessous).

## 3. Assistant opérateur (RAG)

### Architecture
```text
docs/*.md ──► découpage (900 caractères, chevauchement 150)
          ──► embeddings nomic-embed-text (768 dimensions) ──► index FAISS
Question  ──► 3 passages les plus proches ──► qwen2.5:3b (Ollama, PC IA) ──► réponse + sources
```
- Orchestration : **LangChain** ; modèle de langage : **qwen2.5:3b** (3 milliards de paramètres, sous la limite de **8 milliards** du sujet).
- Paramètres : température 0,1 ; réponse limitée à environ 3 phrases (150 jetons) ; fenêtre de contexte 2 048 ; modèle gardé en mémoire 30 min ; délai maximal 120 s.
- Le prompt impose de répondre **uniquement à partir du contexte fourni**, de dire qu'on ne sait pas sinon, et de citer ses sources.

### Interface de consultation
Les opérateurs interrogent l'assistant par une **page web servie par le PC IA** (réseau du groupe, port 8100). Elle s'appuie sur le **même Ollama, le même modèle (`qwen2.5:3b`) et les mêmes documents** que le service `rag-assistant` de la plateforme, et affiche pour chaque réponse les **sources** utilisées et le temps de réponse. Le texte du modèle est affiché comme du texte brut (jamais interprété comme du HTML).

### Choix du modèle et contraintes matérielles
Le PC IA est un portable **sans carte graphique** (processeur i5-10210U, 15,8 Go de RAM) : l'inférence se fait sur le processeur. Un modèle de 3 milliards de paramètres est le compromis retenu : un modèle de 7 à 8 milliards serait plus lourd en mémoire et plus lent sur ce matériel.

| Mesure (PC IA, CPU seul) | Valeur |
|---|---|
| Vitesse de génération, `llama3.2:3b` (modèle d'essai) | environ **11 jetons/s** (mesuré) |
| Chargement du modèle à froid | 10 à 30 s (mesuré) |
| Vitesse de génération, `qwen2.5:3b` (modèle retenu) | non mesurée séparément ; même ordre de grandeur attendu (modèle de même taille) |
| Première réponse après un long silence | plusieurs dizaines de secondes (chargement du modèle) ; plus rapide ensuite, le modèle étant conservé en mémoire (`keep_alive`) |

### Garde-fous de sécurité
- **Lecture seule** : l'assistant ne dispose d'aucun outil, ni du socket Docker, ni d'aucun accès privilégié.
- **Non critique** : si Ollama est injoignable, le service renvoie une erreur 503 propre et rien d'autre n'est impacté.
- **Ollama n'a pas d'authentification** : il n'écoute que sur l'adresse du réseau du groupe (`192.168.137.x`) et le pare-feu Windows n'autorise le port 11434 que pour `192.168.137.0/24`. Il n'est joignable ni depuis le Wi-Fi du campus ni depuis Internet.
- Les documents indexés sont des documents internes de confiance (risque d'injection de consignes via les documents limité à ce périmètre).

### Limites observées
- **Hallucination d'un petit modèle** : lors d'un test, `llama3.2:3b` a répondu sans contexte qu'un WAF protège contre le phishing, ce qui est faux. C'est la raison d'être du RAG et de la consigne « répondre uniquement à partir du contexte ».
- **Latence** sur processeur : la première réponse après un long silence est lente si le modèle a été déchargé de la mémoire.
- **Petit corpus** (quelques documents) : les questions hors sujet reçoivent la réponse « information introuvable ».
- **Pas d'accès à l'état en direct** : l'assistant ne connaît que la documentation, il ne peut pas répondre à « quelle est la dernière attaque ? ». C'est un **choix de sécurité** (lecture seule, aucun accès au système, comme l'exige le sujet) : l'état en direct est fourni par le dashboard de supervision. Plutôt qu'un « introuvable » trompeur, l'interface répond explicitement qu'elle n'a pas accès aux événements en direct et renvoie vers le dashboard.
- **Pas d'évaluation chiffrée à grande échelle** : nous avons validé quelques questions représentatives (voir ci-dessous), pas un jeu de test complet.

### Questions utilisées pour la démonstration
| Question | Comportement attendu |
|---|---|
| « Que fait la remédiation en cas de credential stuffing ? » | Réponse issue du runbook correspondant, avec ses sources |
| « Comment le rate-limiting du WAF est-il levé ? » | Réponse issue du runbook WAF, avec ses sources |
| « Que se passe-t-il si un service tombe ? » | Réponse issue du runbook « service down », avec ses sources |
| « Quelle est la dernière attaque ? » (état en direct) | L'assistant explique qu'il n'a pas accès aux événements en direct et renvoie vers le dashboard |

Nous n'avons pas mené d'évaluation chiffrée de la qualité des réponses : la validation est qualitative, par comparaison avec les runbooks.

## 4. Pistes d'amélioration
- Allonger la baseline et ajouter des mesures (diversité des adresses sources, débit sortant).
- Mettre un reverse proxy avec authentification devant Ollama.
- Fournir à l'assistant un **flux d'incidents en lecture seule** (par exemple l'historique des incidents de la remédiation, via une route dédiée en lecture seule), pour qu'il puisse répondre sur l'état récent sans disposer d'aucun droit d'action.
- Évaluer l'assistant sur un jeu de questions plus large, avec une mesure de fidélité aux sources.
- Utiliser un modèle plus grand si un GPU est disponible.
