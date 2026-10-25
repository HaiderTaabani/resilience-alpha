import hmac
import ipaddress
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
import psycopg
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

TOKEN = os.environ["ORCH_TOKEN"]
WAF_URL = os.environ.get("WAF_URL", "http://waf:8080")
PROBE_USER = os.environ["AUTH_DEMO_USER"]
PROBE_PASSWORD = os.environ["AUTH_DEMO_PASSWORD"]
BLOCK_SECONDS = int(os.environ.get("BLOCK_SECONDS", "300"))
COOLDOWN_SECONDS = 30
# Adresses qu'on ne bloque JAMAIS : la passerelle Docker (172.28.0.128) apparait pour tout
# le trafic venant de ce PC, et 192.168.137.1 est le PC Hote lui-meme.
PROTECTED = [
    ipaddress.ip_network(n.strip())
    for n in os.environ.get("PROTECTED_NETWORKS", "127.0.0.0/8,172.28.0.0/24,192.168.137.1/32").split(",")
]

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
log = logging.getLogger("orchestrator")

INCIDENTS = Counter("incidents_total", "Incidents traites", ["type", "outcome"])
BLOCKS = Counter("ip_blocks_total", "Tentatives de blocage d'IP", ["result"])
DURATION = Histogram("remediation_duration_seconds", "Duree alerte -> verdict", buckets=(2, 5, 10, 20, 30, 60))
ACTIVE = Gauge("incident_active", "Incidents en cours de traitement")

_last_seen: dict = {}


def event(name: str, **fields):
    log.info(json.dumps({"service": "orchestrator", "event": name, **fields}))


def get_conn():
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=3,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_http_server(9100)  # metriques pour Prometheus
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS blocked_ips ("
            "ip TEXT PRIMARY KEY, reason TEXT, "
            "blocked_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS incidents ("
            "id TEXT PRIMARY KEY, type TEXT NOT NULL, ip TEXT, state TEXT NOT NULL, "
            "started_at TIMESTAMPTZ NOT NULL, resolved_at TIMESTAMPTZ, steps JSONB NOT NULL)"
        )
    yield


app = FastAPI(title="RESILIENCE-ALPHA - Orchestrateur", lifespan=lifespan)


class AlertIn(BaseModel):
    type: Literal["bruteforce", "flood"]
    ip: str | None = Field(default=None, max_length=45)
    source: str = Field(default="manuel", max_length=50)


class Incident:
    def __init__(self, type_: str, ip: str | None):
        self.id = uuid.uuid4().hex[:8]
        self.type = type_
        self.ip = ip
        self.state = "open"
        self.started_at = datetime.now(timezone.utc)
        self.resolved_at = None
        self.steps: list = []

    def step(self, name: str, ok: bool, detail: str = ""):
        self.steps.append({"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "step": name, "ok": ok, "detail": detail})
        event("step", incident=self.id, step=name, ok=ok, detail=detail)
        self.save()

    def save(self):
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO incidents (id, type, ip, state, started_at, resolved_at, steps) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (id) DO UPDATE SET state = EXCLUDED.state, "
                "resolved_at = EXCLUDED.resolved_at, steps = EXCLUDED.steps",
                (self.id, self.type, self.ip, self.state, self.started_at,
                 self.resolved_at, Jsonb(self.steps)),
            )


def is_protected(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True  # adresse invalide : on ne la bloque pas
    return any(addr in net for net in PROTECTED)


def block_ip(ip: str, reason: str):
    expires = datetime.now(timezone.utc) + timedelta(seconds=BLOCK_SECONDS)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO blocked_ips (ip, reason, expires_at) VALUES (%s, %s, %s) "
            "ON CONFLICT (ip) DO UPDATE SET reason = EXCLUDED.reason, "
            "blocked_at = now(), expires_at = EXCLUDED.expires_at",
            (ip, reason, expires),
        )


def probe() -> tuple[bool, str]:
    """Preuve de reprise : on se comporte comme un vrai client, via le WAF.
    /health, puis connexion, puis une vraie transaction fictive."""
    headers = {"User-Agent": "resilience-orchestrator/1.0"}
    try:
        with httpx.Client(timeout=3, headers=headers) as c:
            r = c.get(f"{WAF_URL}/health")
            if r.status_code != 200:
                return False, f"/health -> {r.status_code}"
            r = c.post(f"{WAF_URL}/login", json={"username": PROBE_USER, "password": PROBE_PASSWORD})
            if r.status_code != 200:
                return False, f"/login -> {r.status_code}"
            token = r.json()["access_token"]
            r = c.post(f"{WAF_URL}/transactions",
                       json={"from_account": "PROBE01", "to_account": "PROBE02", "amount": 1.00},
                       headers={"Authorization": f"Bearer {token}"})
            if r.status_code != 201:
                return False, f"/transactions -> {r.status_code}"
            return True, f"transaction #{r.json()['id']} enregistree"
    except Exception as exc:
        return False, f"erreur : {type(exc).__name__}"


def run_incident(inc: Incident):
    t0 = time.monotonic()
    ACTIVE.inc()
    try:
        inc.step("alerte_recue", True, f"type={inc.type} ip={inc.ip}")

        ok, detail = probe()
        inc.step("etat_pendant_incident", ok, detail)

        acted = False
        if not inc.ip:
            inc.step("blocage_ip", False, "aucune IP fournie dans l'alerte")
            BLOCKS.labels("sans_ip").inc()
        elif is_protected(inc.ip):
            inc.step("blocage_ip", False,
                     f"{inc.ip} non bloquable (passerelle/interne) : l'IP source est masquee par Docker")
            BLOCKS.labels("refuse_protege").inc()
        else:
            block_ip(inc.ip, f"{inc.type} (incident {inc.id})")
            inc.step("blocage_ip", True, f"{inc.ip} bloquee {BLOCK_SECONDS} s")
            BLOCKS.labels("ok").inc()
            acted = True

        ok, detail = False, "non execute"
        for attempt in range(1, 11):  # le cache de l'API se rafraichit toutes les 2 s
            ok, detail = probe()
            if ok:
                break
            time.sleep(2)
        inc.step("verification_transaction", ok, f"{detail} (essai {attempt}/10)")

        if not ok:
            inc.state = "failed"
        elif acted:
            inc.state = "resolved"
        else:
            inc.state = "unmitigated"  # le service marche mais on n'a rien pu faire contre la source
    except Exception as exc:
        inc.state = "failed"
        event("incident_error", incident=inc.id, error=type(exc).__name__)
    finally:
        inc.resolved_at = datetime.now(timezone.utc)
        try:
            inc.save()
        except Exception:
            pass
        elapsed = time.monotonic() - t0
        DURATION.observe(elapsed)
        INCIDENTS.labels(inc.type, inc.state).inc()
        ACTIVE.dec()
        event("incident_closed", incident=inc.id, state=inc.state, seconds=round(elapsed, 1))


def require_token(x_alert_token: str | None):
    if not x_alert_token or not hmac.compare_digest(x_alert_token, TOKEN):
        raise HTTPException(status_code=401, detail="jeton d'alerte invalide")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/alert", status_code=202)
def alert(a: AlertIn, background: BackgroundTasks, x_alert_token: str | None = Header(default=None)):
    require_token(x_alert_token)
    key = (a.type, a.ip)
    now = time.monotonic()
    if now - _last_seen.get(key, -1e9) < COOLDOWN_SECONDS:
        return {"status": "ignoree", "reason": "meme alerte deja traitee il y a moins de 30 s"}
    _last_seen[key] = now
    inc = Incident(a.type, a.ip)
    inc.save()
    background.add_task(run_incident, inc)
    return {"status": "acceptee", "incident": inc.id}


@app.get("/incidents")
def incidents(x_alert_token: str | None = Header(default=None)):
    require_token(x_alert_token)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, type, ip, state, started_at, resolved_at, steps "
            "FROM incidents ORDER BY started_at DESC LIMIT 20"
        ).fetchall()
    return [{"id": r[0], "type": r[1], "ip": r[2], "state": r[3],
             "started_at": r[4], "resolved_at": r[5], "steps": r[6]} for r in rows]
