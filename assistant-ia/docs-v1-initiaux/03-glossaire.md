# Glossaire

## WAF
Web Application Firewall : pare-feu qui lit le contenu des requêtes web et bloque celles qui ressemblent à une attaque connue, comme une injection SQL ou du cross-site scripting.

## Prometheus
Outil qui relève des métriques (des chiffres) à intervalle régulier, ici toutes les 5 secondes, et les garde dans le temps.

## Loki
Outil qui stocke les logs, c'est-à-dire les messages d'événements des services, avec des étiquettes comme le nom du service.

## Grafana
Outil qui affiche sur un écran les métriques de Prometheus et les logs de Loki.

## JWT
Jeton signé qui prouve l'identité d'un utilisateur pendant une durée limitée. Il est délivré par le service d'authentification après une connexion réussie.

## Credential stuffing
Attaque qui consiste à essayer un très grand nombre d'identifiants et de mots de passe sur une page de connexion.

## Flood
Envoi d'un très grand nombre de requêtes pour saturer un service.

## Isolation Forest
Algorithme de machine learning qui apprend ce qui est normal à partir de mesures, puis repère les mesures qui s'en écartent.

## Remédiation
Réparation automatique d'un service après la détection d'un incident, suivie d'une vérification.

## Healthcheck
Test que Docker exécute régulièrement pour savoir si un conteneur fonctionne vraiment, et pas seulement s'il est démarré.

## RAG
Technique où l'assistant cherche d'abord des passages dans la documentation, puis rédige sa réponse à partir de ces passages, pour éviter d'inventer.

## PCA et PRA
Plan de continuité d'activité, qui permet de continuer à fonctionner pendant une crise, et plan de reprise d'activité, qui permet de redémarrer après.
