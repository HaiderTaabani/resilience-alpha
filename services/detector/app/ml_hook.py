"""Point de branchement du modele de machine learning.

Le detecteur appelle predict() toutes les 5 secondes avec les mesures du moment.
Pour brancher le vrai modele : remplacer le corps de predict() (charger le modele une
seule fois au niveau du module, puis l'appeler ici). Le reste du detecteur ne change pas.
"""

# Ordre et noms des mesures donnees au modele (ce sont les colonnes des donnees d'entrainement).
FEATURES = ["login_fail_rate", "request_rate", "unauthorized_rate", "latency_p95"]


def predict(features: dict):
    """Renvoie "bruteforce", "flood" ou None (rien d'anormal).

    features : dict {nom: valeur} avec les cles de FEATURES, par exemple
        {"login_fail_rate": 0.0, "request_rate": 0.8, "unauthorized_rate": 0.0, "latency_p95": 0.02}

    Exemple de branchement (a adapter) :
        x = [[features[name] for name in FEATURES]]
        if model.predict(x)[0] == -1:          # -1 = anomalie pour un IsolationForest
            return "bruteforce" if features["login_fail_rate"] > features["request_rate"] / 2 else "flood"
        return None
    """
    return None  # pas de modele pour l'instant : seules les regles a seuil decident
