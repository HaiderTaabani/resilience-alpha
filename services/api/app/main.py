import os
import time
from contextlib import asynccontextmanager
from decimal import Decimal

import httpx
import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, start_http_server
from pydantic import BaseModel, Field


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Table lue par l'API et ecrite par l'orchestrateur : les IP bloquees, avec expiration.
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS blocked_ips ("
            "ip TEXT PRIMARY KEY, reason TEXT, "
            "blocked_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
            "expires_at TIMESTAMPTZ NOT NULL)"
        )
    yield


app = FastAPI(title="RESILIENCE-ALPHA - API metier", lifespan=lifespan)

REQUESTS = Counter(
    "http_requests_total", "Requetes HTTP recues", ["method", "path", "status"]
)
LATENCY = Histogram("http_request_duration_seconds", "Duree des requetes", ["path"])

# Les metriques sortent sur un port a part (9100) : le WAF ne les expose jamais.
start_http_server(9100)


_blocked = {"checked_at": 0.0, "ips": set()}


def client_ip(request: Request) -> str:
    """IP du client telle que le WAF l'a vue.

    On prend la DERNIERE valeur de X-Forwarded-For : c'est celle ajoutee par notre WAF.
    La premiere pourrait etre inventee par l'attaquant.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host


def blocked_ips() -> set:
    """Liste des IP bloquees, relue dans la base au plus toutes les 2 secondes."""
    if time.monotonic() - _blocked["checked_at"] > 2:
        try:
            with get_conn() as conn:
                rows = conn.execute(
                    "SELECT ip FROM blocked_ips WHERE expires_at > now()"
                ).fetchall()
            _blocked["ips"] = {r[0] for r in rows}
        except Exception:
            pass  # base indisponible : on garde la derniere liste connue
        _blocked["checked_at"] = time.monotonic()
    return _blocked["ips"]


@app.middleware("http")
async def collect_metrics(request: Request, call_next):
    start = time.perf_counter()
    is_blocked = client_ip(request) in blocked_ips()
    if is_blocked:
        response = JSONResponse({"detail": "ip bloquee"}, status_code=403)
    else:
        response = await call_next(request)
    route = request.scope.get("route")
    # Gabarit de la route ("/transactions"), "inconnue" sinon : un attaquant ne peut
    # pas faire exploser le nombre de series en inventant des URL.
    path = "bloquee" if is_blocked else (route.path if route else "inconnue")
    REQUESTS.labels(request.method, path, str(response.status_code)).inc()
    LATENCY.labels(path).observe(time.perf_counter() - start)
    return response


def get_conn():
    return psycopg.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        connect_timeout=3,
    )


JWT_SECRET = os.environ["JWT_SECRET"]
AUTH_URL = os.environ["AUTH_URL"]


def require_user(authorization: str | None = Header(default=None)) -> str:
    """Verifie le jeton JWT envoye par le client. Renvoie le nom de l'utilisateur."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="jeton manquant")
    try:
        payload = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="jeton invalide ou expire")
    return payload["sub"]


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)


class TransactionIn(BaseModel):
    from_account: str = Field(min_length=1, max_length=34)
    to_account: str = Field(min_length=1, max_length=34)
    amount: Decimal = Field(gt=0, le=10000, decimal_places=2)


@app.get("/health")
def health():
    """Sert a la supervision et a la preuve de reprise : l'API ET la base repondent."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="base de donnees injoignable")
    return {"status": "ok", "db": "ok"}


@app.post("/login")
def login(creds: LoginIn, request: Request):
    """Relaie la demande au service d'auth interne (le WAF n'expose qu'une seule porte)."""
    try:
        r = httpx.post(
            f"{AUTH_URL}/login",
            json=creds.model_dump(),
            headers={"X-Client-IP": client_ip(request)},
            timeout=3,
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="service d'authentification injoignable")
    if r.status_code == 401:
        raise HTTPException(status_code=401, detail="identifiants invalides")
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail="erreur du service d'authentification")
    return r.json()


@app.post("/transactions", status_code=201)
def create_transaction(tx: TransactionIn, user: str = Depends(require_user)):
    with get_conn() as conn:
        row = conn.execute(
            "INSERT INTO transactions (from_account, to_account, amount) "
            "VALUES (%s, %s, %s) RETURNING id, created_at",
            (tx.from_account, tx.to_account, tx.amount),
        ).fetchone()
    return {"id": row[0], "status": "OK", "created_at": row[1]}


@app.get("/transactions")
def list_transactions(limit: int = 20, user: str = Depends(require_user)):
    limit = max(1, min(limit, 100))
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, from_account, to_account, amount, status, created_at "
            "FROM transactions ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [
        {
            "id": r[0],
            "from_account": r[1],
            "to_account": r[2],
            "amount": r[3],
            "status": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]
