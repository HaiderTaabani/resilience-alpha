# Partie IA / Data

*Qui a fait quoi : le détecteur ML et le service d'assistant de la plateforme sont d'Ismael. Le PC IA (Ollama, réseau, pare-feu), la page de consultation et cette partie du dossier sont de Haider.*

## 1. Deux IA, des rôles séparés

| Composant | À quoi il sert | Peut agir sur le système ? |
|---|---|---|
| **Détecteur d'anomalies** | Repère un comportement anormal et prévient la remédiation | Non, il alerte seulement |
| **Assistant opérateur** | Explique la procédure à un opérateur, à partir de la documentation | Non, aucun accès au système |
| **Remédiation** (automate) | Répare le service et vérifie la reprise | Oui, c'est le seul |

Aucune donnée réelle n'est utilisée. Le modèle de langage tourne en local : rien ne sort du réseau du groupe.

## 2. Détection d'anomalies

**Principe.** Toutes les 5 secondes, le détecteur lit quatre mesures dans Prometheus : le nombre de requêtes par seconde, la latence, le taux d'erreurs et le nombre d'échecs de connexion par seconde. En trafic normal, nous avons mesuré environ 0,3 requête/s et aucun échec de connexion.

**Modèle.** Un **Isolation Forest** (scikit-learn), qui apprend ce qui est « normal » pendant environ une minute (12 mesures), puis repère ce qui s'en écarte. Nous l'avons choisi parce qu'il est **non supervisé** (nous n'avons pas d'exemples d'attaques étiquetés), léger et rapide.

**Le modèle ne décide jamais seul.**
- *Panne franche* : un service injoignable pendant 2 mesures déclenche directement la remédiation.
- *Règles simples* : au moins 2 échecs de connexion par seconde (credential stuffing) ou 8 requêtes par seconde (flood).
- *Anomalie du modèle* : confirmée seulement si elle dure 3 mesures de suite **et** qu'un symptôme concret l'accompagne (erreurs, échecs de connexion ou forte latence).
- Après un incident, le détecteur attend 45 secondes avant d'en déclencher un autre.

Les attaques franches ne servent jamais à entraîner le modèle, pour qu'il n'apprenne pas l'attaque comme du trafic normal.

**Résultat mesuré.** Reprise après la panne d'un service : **13 secondes** (mesure de l'équipe).

**Limites.**
- Au départ, le modèle déclenchait à tort sur des pics isolés. Nous avons réduit sa sensibilité et ajouté l'exigence d'un symptôme concret.
- Il n'apprend que pendant une minute, sur un trafic de laboratoire très faible : les seuils ne seraient pas valables tels quels en production.
- Une attaque très lente pourrait passer sous les seuils.
- Nous n'avons pas mesuré le taux de faux positifs de façon systématique : il s'observe sur le dashboard.

## 3. Assistant opérateur

**Principe (RAG).** Un petit modèle de langage invente facilement. L'assistant **cherche d'abord** dans nos documents (architecture, runbooks, paramètres du détecteur et du WAF), puis rédige sa réponse **uniquement** à partir de ce qu'il a trouvé, et **cite ses sources**.

```text
Question ──► recherche des 3 passages les plus proches ──► modèle (Ollama) ──► réponse + sources
```

**Outils.** Ollama (le modèle tourne sur le PC IA), LangChain, le modèle **qwen2.5:3b** (3 milliards de paramètres, sous la limite de 8 milliards du sujet) et le modèle de recherche nomic-embed-text.

**Pourquoi un petit modèle.** Le PC IA n'a pas de carte graphique : le modèle tourne sur le processeur. Un modèle de 3 milliards de paramètres reste utilisable ; un modèle de 7 à 8 milliards serait plus lent sur ce matériel. Nous avons mesuré environ **11 mots par seconde** sur un modèle de même taille (`llama3.2:3b`). La première réponse après un long silence peut prendre plusieurs dizaines de secondes (chargement du modèle), puis c'est plus rapide.

**Comment on l'utilise.** Une page web servie par le PC IA (réseau du groupe) : l'opérateur tape sa question et voit la réponse, ses sources et le temps de réponse. Elle utilise le même Ollama, le même modèle et les mêmes documents que le service d'assistant de la plateforme.

**Sécurité.**
- **Lecture seule** : aucun accès au système, à Docker ou aux autres services.
- **Non critique** : si le PC IA est injoignable, l'assistant répond par une erreur propre et le reste de la plateforme n'est pas touché.
- **Ollama n'a pas de mot de passe** : il n'écoute que sur l'adresse du réseau du groupe, et le pare-feu n'autorise le port qu'à ce réseau. Il n'est visible ni depuis le Wi-Fi du campus, ni depuis Internet.

**Limites.**
- Un petit modèle peut inventer : lors d'un test, il a affirmé qu'un pare-feu applicatif (WAF) protège contre le phishing, ce qui est faux. C'est la raison d'être du RAG.
- L'assistant **ne connaît que la documentation** : il ne peut pas dire « quelle est la dernière attaque ? ». C'est un choix de sécurité voulu (lecture seule). Il l'explique clairement et renvoie vers le dashboard, qui montre l'état en direct.
- Peu de documents : une question hors sujet reçoit « information introuvable ».
- La qualité des réponses est vérifiée à la main, en comparant avec les runbooks. Nous n'avons pas fait d'évaluation chiffrée.

**Questions de démonstration** : « Que fait la remédiation en cas de credential stuffing ? », « Comment le rate-limiting du WAF est-il levé ? », « Que se passe-t-il si un service tombe ? »

## 4. Pistes d'amélioration
- Allonger la période d'apprentissage du modèle et ajouter des mesures.
- Placer un proxy avec authentification devant Ollama.
- Donner à l'assistant un flux d'incidents **en lecture seule**, pour qu'il puisse parler des événements récents sans aucun droit d'action.
- Évaluer l'assistant sur un jeu de questions plus large.
