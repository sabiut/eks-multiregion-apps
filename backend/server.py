"""The backend tier of the lab: a small JSON API. The frontend tier (nginx) forwards /api/ to
it; it is the only tier that talks to the database.

  /api/info    who answered: version, region, pod, and what it knows about its secrets
  /api/visits  GET: the visit count from the database.  POST: add one
  /api/burn    use CPU for a moment, to make the autoscaler add pods:  /api/burn?ms=500
  /healthz     liveness: the process is running
  /readyz      readiness: ready for traffic (rollouts and the Service look at this)
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

SECRET_DIR = os.environ.get("SECRET_DIR", "/secrets")
STARTED = time.time()

# Without a database (a laptop, unit tests) the count lives in memory, per pod.
_memory = {"visits": 0}
_lock = threading.Lock()


def read_secret(name):
    """Secrets arrive as files in a mounted volume. Reading on every request means a rotated
    secret is picked up without restarting the pod."""
    try:
        with open(os.path.join(SECRET_DIR, name), encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def database_settings():
    """Connection details come from Vault, as files. None when no database is configured."""
    host = read_secret("DB_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": read_secret("DB_PORT") or "5432",
        "dbname": read_secret("DB_NAME") or "postgres",
        "user": read_secret("DB_USER"),
        "password": read_secret("DB_PASSWORD"),
        # Encrypt the connection to RDS. Only the integration test turns this off.
        "sslmode": os.environ.get("DB_SSLMODE", "require"),
        "connect_timeout": 3,
    }


def schema():
    """Each environment keeps its rows in its own schema, so dev, stg and prd can share one
    database instance in the lab. In production each would have its own instance."""
    name = os.environ.get("ENVIRONMENT", "local")
    return "".join(ch for ch in name if ch.isalnum() or ch == "_") or "local"


def visits(add):
    """Return (count, where it is stored). Raises if the database refuses."""
    settings = database_settings()
    if settings is None:
        with _lock:
            _memory["visits"] += 1 if add else 0
            return _memory["visits"], "memory (no database configured)"
    import psycopg  # imported here so the unit tests need no database driver

    table = f'"{schema()}".visits'
    with psycopg.connect(**settings) as connection:
        if add:
            # Fails on a read replica: a standby region cannot write until it is promoted.
            connection.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema()}"')
            connection.execute(f"CREATE TABLE IF NOT EXISTS {table} (id int PRIMARY KEY, count bigint NOT NULL)")
            connection.execute(
                f"INSERT INTO {table} VALUES (1, 1) ON CONFLICT (id) DO UPDATE SET count = visits.count + 1"
            )
        try:
            row = connection.execute(f"SELECT count FROM {table} WHERE id = 1").fetchone()
        except psycopg.errors.UndefinedTable:
            # Nothing has been recorded yet, so the table does not exist: the count is zero.
            # (Covered by test_postgres.py against a real database.)
            row = None
        return (row[0] if row else 0), "postgres"


def identity():
    return {
        "app": "demo-api",
        "tier": "backend",
        "environment": os.environ.get("ENVIRONMENT", "local"),
        "version": os.environ.get("VERSION", "dev"),
        "region": os.environ.get("REGION", "local"),
        "pod": os.environ.get("POD_NAME", "local"),
        "node": os.environ.get("NODE_NAME", "local"),
        "greeting": read_secret("GREETING") or "no secret mounted",
        # Never return a secret's value. Showing that it exists is enough.
        "api_key_loaded": read_secret("API_KEY") is not None,
        "database_configured": database_settings() is not None,
    }


def burn(milliseconds):
    end = time.time() + min(milliseconds, 5000) / 1000
    count = 0
    while time.time() < end:
        count += 1
    return count


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def reply_visits(self, add):
        try:
            count, store = visits(add)
            self.reply(200, {"visits": count, "store": store, "pod": os.environ.get("POD_NAME", "local")})
        except Exception as error:  # noqa: BLE001 (report any database failure as 503)
            # The error class only. A full message could include connection details.
            self.reply(503, {"error": "database unavailable or read-only", "kind": type(error).__name__})

    def do_GET(self):  # noqa: N802 (name set by the standard library)
        url = urlparse(self.path)
        if url.path == "/healthz":
            self.reply(200, {"status": "alive"})
        elif url.path == "/readyz":
            # Not ready for the first seconds, like an application warming up. Readiness does
            # not depend on the database: if it did, a database outage would empty the
            # Service and hide the real error.
            ready = time.time() - STARTED >= float(os.environ.get("STARTUP_SECONDS", "3"))
            self.reply(200 if ready else 503, {"ready": ready})
        elif url.path == "/api/burn":
            ms = int(parse_qs(url.query).get("ms", ["200"])[0])
            self.reply(200, {"burned_ms": ms, "loops": burn(ms), "pod": os.environ.get("POD_NAME", "local")})
        elif url.path == "/api/visits":
            self.reply_visits(add=False)
        elif url.path in ("/api/info", "/"):
            self.reply(200, identity())
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if urlparse(self.path).path == "/api/visits":
            self.reply_visits(add=True)
        else:
            self.reply(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        # One JSON line per request on stdout: the container runtime collects it.
        if self.path not in ("/healthz", "/readyz"):
            print(json.dumps({"path": self.path, "status": args[1] if len(args) > 1 else ""}), flush=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(json.dumps({"msg": "listening", "port": port}), flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
