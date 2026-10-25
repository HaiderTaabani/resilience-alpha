# Architecture de la plateforme RESILIENCE-ALPHA (version initiale)

Cette documentation décrit la plateforme du consortium au 21 octobre 2026. En cas de doute, le fichier docker-compose.yml du dépôt fait foi.

## Vue d'ensemble

La plateforme de paiement est fictive. Elle tourne sur le PC Hôte avec Docker Compose. Un second ordinateur, le PC Attaquant, sert à déclencher les scénarios offensifs. Un troisième ordinateur, le PC IA, héberge uniquement Ollama et l'assistant des opérateurs.

Il y a deux réseaux Docker. Le réseau appnet est interne : il contient la base, l'authentification et l'API. Le réseau monitornet contient la surveillance et les composants qui doivent être joints depuis l'extérieur.

## Les services

- db : base de données PostgreSQL 16. Elle stocke les comptes et les transactions fictives.
- auth : service d'authentification en Node.js, port interne 4000. Il gère l'inscription et la connexion (login) et délivre un jeton JWT. Il publie des métriques pour Prometheus.
- api : API métier en Node.js, port interne 3000. Elle traite les paiements, les soldes et les bénéficiaires.
- waf-auth : pare-feu applicatif (WAF) ModSecurity avec les règles OWASP CRS devant le service auth. Accessible sur le port 18081 du PC Hôte.
- waf-api : même WAF devant l'API. Accessible sur le port 18080 du PC Hôte.
- detector : détecteur d'anomalies en Python, port 9100. Il lit Prometheus toutes les 5 secondes.
- remediation : moteur de remédiation en Node.js, port 5000. Il reçoit les incidents et répare automatiquement.
- frontend : pages web de connexion, de paiement et dashboard de supervision, port 8090.
- prometheus (port 9090) : relève les métriques toutes les 5 secondes.
- loki (port 3100) : stocke les logs des conteneurs.
- grafana (port 3000) : affiche les métriques et les logs.

## Le trajet d'un incident

1. Le PC Attaquant envoie un trafic anormal vers la plateforme.
2. Prometheus mesure le nombre de requêtes par seconde, les échecs de connexion et la latence. Loki conserve les logs.
3. Le détecteur compare ces mesures au comportement habituel avec des règles à seuil et un modèle Isolation Forest.
4. S'il confirme une anomalie, il envoie un incident au moteur de remédiation.
5. La remédiation redémarre le service touché, attend qu'il soit sain, puis vérifie la reprise par un vrai paiement de test.
6. Le dashboard affiche l'état avant, pendant et après l'incident.

## Les comptes de test

La remédiation utilise deux comptes fictifs de vérification, probe1 et probe2. Elle effectue un paiement de 1 unité de probe1 vers probe2 pour prouver que la plateforme fonctionne de nouveau.
