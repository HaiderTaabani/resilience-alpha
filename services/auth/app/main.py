import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import psycopg
from fastapi import FastAPI, Header, HTTPException
from prometheus_client import Counter, start_http_server
from pydantic import BaseModel, Field

LOGINS = Counter("login_attempts_total", "Tentatives de connexion", ["result"])

JWT_SECRET = os.environ["JWT_SECRET"]
TOKEN_LIFETIME = timedelta(minutes=15)

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
log = logging.getLogger("auth")


def event(name: str, **fields):
    """Une ligne JSON par evenement : c'est ce que Loki collectera et que la detection lira."""
    log.info(json.dumps({"service": "auth", "event": name, **fields}))


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
    start_http_server(9100)  # metriques pour Prometheus (port interne uniquement)
    # Cree la table des utilisateurs et un compte de demonstration (fictif).
    with get_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "username VARCHAR(50) PRIMARY KEY, password_hash TEXT NOT NULL)"
        )
        demo_user = os.environ["AUTH_DEMO_USER"]
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = %s", (demo_user,)
        ).fetchone()
        if not exists:
            pw_hash = bcrypt.hashpw(
                os.environ["AUTH_DEMO_PASSWORD"].encode(), bcrypt.gensalt()
            ).decode()
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s)",
                (demo_user, pw_hash),
            )
    yield


app = FastAPI(title="RESILIENCE-ALPHA - Auth", lifespan=lifespan)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=72)


@app.post("/login")
def login(creds: LoginIn, x_client_ip: str | None = Header(default=None)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = %s", (creds.username,)
        ).fetchone()

    ok = row is not None and bcrypt.checkpw(creds.password.encode(), row[0].encode())
    if not ok:
        LOGINS.labels("failed").inc()
        event("login_failed", username=creds.username, client_ip=x_client_ip)
        # Meme message que le compte existe ou non : on ne renseigne pas l'attaquant.
        raise HTTPException(status_code=401, detail="identifiants invalides")

    LOGINS.labels("ok").inc()
    event("login_ok", username=creds.username, client_ip=x_client_ip)
    token = jwt.encode(
        {"sub": creds.username, "exp": datetime.now(timezone.utc) + TOKEN_LIFETIME},
        JWT_SECRET,
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}
