# Procédures de réponse aux incidents

## Rafale d'échecs de connexion (credential stuffing)

Signes : le taux d'échecs de connexion atteint ou dépasse 3 échecs par seconde, la latence de l'authentification augmente (la vérification des mots de passe consomme du processeur), et le dashboard passe en anomalie.

Réaction automatique : le détecteur envoie un incident de type credential_stuffing à la remédiation. La remédiation applique la stratégie restart_shed_load : elle redémarre le service auth, attend qu'il soit sain, puis vérifie la reprise par une connexion et un paiement de test.

Vérifications de l'opérateur : le statut de la remédiation doit passer de remediating à recovered. Dans Loki, le service remediation doit journaliser remediation_success. Dans Grafana, la latence doit redescendre.

## Flood de requêtes

Signes : le débit atteint ou dépasse 8 requêtes par seconde sur le service surveillé, alors que le trafic normal est d'environ 0,3 requête par seconde.

Réaction automatique : identique à la rafale d'échecs de connexion, avec la raison flood.

## Panne franche d'un service

Signes : Prometheus voit la cible injoignable (up égal à 0) sur 2 fenêtres de mesure consécutives.

Réaction automatique : le détecteur envoie un incident de type service_down. La remédiation relance le conteneur, même s'il est arrêté, puis vérifie la reprise.

## Éviter les faux positifs

Le modèle Isolation Forest seul ne suffit pas à déclencher une réparation. Une anomalie est confirmée seulement si le modèle la signale sur au moins 3 fenêtres consécutives et si un signal concret la corrobore : erreurs 5xx, échecs de connexion d'au moins 1 par seconde, ou latence p95 d'au moins 1000 millisecondes. Après un incident, le détecteur attend 45 secondes avant d'en déclencher un autre.

## Les statuts de la remédiation

- idle : rien à traiter.
- remediating : une réparation est en cours.
- recovered : le service a redémarré et la transaction de vérification a réussi.
- failed : le service n'a pas pu être rétabli après deux tentatives.

## Que faire si la remédiation est en échec

Hors démonstration, un opérateur peut consulter les logs du service remediation dans Loki, vérifier l'état des conteneurs avec docker compose ps, puis relancer le service concerné. Pendant la démonstration devant le jury, aucune intervention humaine n'est permise : si la reprise échoue, l'axe remédiation est noté zéro.

## Ce que l'assistant ne fait pas

L'assistant explique et retrouve des informations dans la documentation. Il ne redémarre aucun service, ne bloque aucune adresse et n'a aucun accès privilégié au système. Seule la remédiation automatique agit.
