import json
import logging
import math
import os
import sys
import time

import httpx
from prometheus_client import Counter, Gauge, start_http_server

from ml_hook import FEATURES, predict

PROM_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
ORCH_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
TOKEN = os.environ["ORCH_TOKEN"]

TICK_SECONDS = float(os.environ.get("TICK_SECONDS", "5"))
FAIL_RATE_THRESHOLD = float(os.environ.get("FAIL_RATE_THRESHOLD", "1.0"))    # echecs de connexion / s
FLOOD_RATE_THRESHOLD = float(os.environ.get("FLOOD_RATE_THRESHOLD", "30"))   # requetes / s
CONFIRM_TICKS = int(os.environ.get("CONFIRM_TICKS", "2"))                    # mesures de suite avant alerte
ALERT_COOLDOWN = float(os.environ.get("ALERT_COOLDOWN_SECONDS", "60"))

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # sinon 1 ligne de log par requete Prometheus
log = logging.getLogger("detector")

FEATURE_GAUGE = Gauge("detector_feature", "Mesures lues par le detecteur", ["name"])
ALERTS = Counter("detector_alerts_total", "Alertes envoyees a l'orchestrateur", ["type", "source", "result"])

# Les "mesures" : chaque requete Prometheus donne un nombre.
QUERIES = {
    "login_fail_rate": 'sum(rate(login_attempts_total{result="failed"}[30s]))',
    # path!="bloquee" : une fois l'IP bloquee, ses requetes refusees ne comptent plus comme un flood
    "request_rate": 'sum(rate(http_requests_total{path!="bloquee"}[30s]))',
    "unauthorized_rate": 'sum(rate(http_requests_total{status=~"401|403"}[30s]))',
    "latency_p95": "histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[1m])))",
}

# Pour trouver l'origine : l'IP la plus frequente dans les logs de la derniere minute.
SOURCE_QUERIES = {
    "bruteforce": ('topk(1, sum by (client_ip) (count_over_time({service="auth"} |= "login_failed" | json [1m])))',
                   "client_ip"),
    "flood": ('topk(1, sum by (ip) (count_over_time({service="waf"} '
              '| regexp `^(?P<ip>\\d+\\.\\d+\\.\\d+\\.\\d+) - -` | ip != "" [1m])))', "ip"),
}


def event(name: str, **fields):
    log.info(json.dumps({"service": "detector", "event": name, **fields}))


def prom_value(client: httpx.Client, expr: str) -> float:
    r = client.get(f"{PROM_URL}/api/v1/query", params={"query": expr})
    r.raise_for_status()
    result = r.json()["data"]["result"]
    if not result:
        return 0.0  # aucune serie : rien ne s'est passe
    value = float(result[0]["value"][1])
    return 0.0 if math.isnan(value) else value


def read_features(client: httpx.Client) -> dict:
    return {name: prom_value(client, expr) for name, expr in QUERIES.items()}


def find_source(client: httpx.Client, kind: str):
    query, label = SOURCE_QUERIES[kind]
    try:
        r = client.get(f"{LOKI_URL}/loki/api/v1/query", params={"query": query})
        r.raise_for_status()
        result = r.json()["data"]["result"]
        ip = result[0]["metric"].get(label) if result else None
        return ip or None
    except Exception as exc:
        event("source_error", kind=kind, error=type(exc).__name__)
        return None


def send_alert(client: httpx.Client, kind: str, ip, source: str) -> str:
    try:
        r = client.post(f"{ORCH_URL}/alert", json={"type": kind, "ip": ip, "source": source},
                        headers={"X-Alert-Token": TOKEN})
        return "acceptee" if r.status_code == 202 else f"http_{r.status_code}"
    except Exception as exc:
        return type(exc).__name__


def main():
    start_http_server(9100)
    event("started", fail_threshold=FAIL_RATE_THRESHOLD, flood_threshold=FLOOD_RATE_THRESHOLD,
          confirm_ticks=CONFIRM_TICKS, tick=TICK_SECONDS)
    streak = {"bruteforce": 0, "flood": 0}
    last_alert = {"bruteforce": -1e9, "flood": -1e9}

    with httpx.Client(timeout=5) as client:
        while True:
            started = time.monotonic()
            try:
                features = read_features(client)
            except Exception as exc:
                event("prometheus_error", error=type(exc).__name__)
                time.sleep(TICK_SECONDS)
                continue

            for name in FEATURES:
                FEATURE_GAUGE.labels(name).set(features.get(name, 0.0))

            by_rule = {
                "bruteforce": features["login_fail_rate"] > FAIL_RATE_THRESHOLD,
                "flood": features["request_rate"] > FLOOD_RATE_THRESHOLD,
            }
            try:
                by_ml = predict(features)
            except Exception as exc:
                event("ml_error", error=type(exc).__name__)
                by_ml = None

            for kind in streak:
                suspicious = by_rule[kind] or by_ml == kind
                streak[kind] = streak[kind] + 1 if suspicious else 0
                if streak[kind] < CONFIRM_TICKS:
                    continue
                if time.monotonic() - last_alert[kind] < ALERT_COOLDOWN:
                    continue
                source = "ml" if by_ml == kind else "regle"
                ip = find_source(client, kind)
                result = send_alert(client, kind, ip, source)
                last_alert[kind] = time.monotonic()
                ALERTS.labels(kind, source, result).inc()
                event("alert_sent", type=kind, ip=ip, source=source, result=result,
                      features={k: round(v, 3) for k, v in features.items()})

            time.sleep(max(0.0, TICK_SECONDS - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
