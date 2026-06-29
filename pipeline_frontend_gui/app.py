"""FastAPI backend for the pipeline dashboard.

Endpoints:
    GET  /                      -> static/index.html
    GET  /api/health            -> env + DB reachability check
    GET  /api/status            -> report artifacts + current run state
    POST /api/run               -> spawn `python main.py --phase <ph> ...` (single-run lock)
    GET  /api/logs/{run_id}     -> SSE live log stream from the running subprocess
    GET  /api/runs/{run_id}     -> status / exit code of a run
    POST /api/stop              -> terminate the active run
    GET  /api/results           -> DashboardGenerator().build_payload() as JSON
    GET  /api/config            -> config/ml_config.json
    POST /api/config            -> write config/ml_config.json (validated, atomic)
    GET  /api/reports/{name}    -> serve a file from reports/

State is in-memory (single-user local dev tool). pragmaticefficient: one run at a
time via a module-level lock; subprocess stdout is line-buffered into a per-run
list polled by the SSE coroutine (no queues/locks needed at this scale).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import socket
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
CONFIG_PATH = PROJECT_ROOT / "config" / "ml_config.json"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# Report artifacts exposed in the UI (name -> filename, kind, mime).
REPORT_ARTIFACTS = [
    {"name": "ml_results", "file": "ml_results.json", "label": "ML Results (JSON)", "kind": "json"},
    {"name": "ml_report", "file": "ml_analysis_report_enhanced.html", "label": "ML Analysis Report (HTML)", "kind": "html"},
    {"name": "dashboard", "file": "dashboard.html", "label": "Static Dashboard (HTML)", "kind": "html"},
    {"name": "validation", "file": "validation_report.txt", "label": "Validation Report", "kind": "text"},
    {"name": "reconciliation", "file": "reconciliation_report.txt", "label": "Reconciliation Report", "kind": "text"},
    {"name": "etl_log", "file": "etl.log", "label": "ETL Log", "kind": "text"},
]

VALID_PHASES = [
    "extract", "transform", "load-staging", "reconcile", "create-dw", "load-dw",
    "aggregation", "validate", "ml-pipeline", "ml-report", "dashboard", "all",
]

# ---- in-memory run state ----------------------------------------------------
_runs: dict[str, dict[str, Any]] = {}
_current_run_id: Optional[str] = None
_lock = threading.Lock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _active_run() -> Optional[dict[str, Any]]:
    rid = _current_run_id
    return _runs.get(rid) if rid else None


# ---- local runner preflight -------------------------------------------------
RUNNER = "local"
INSTALL_HINT = "Run `python -m pip install -r requirements.txt`."
_REQUIRED_DEPS = {
    "pandas": "pandas",
    "numpy": "numpy",
    "psycopg2-binary": "psycopg2",
    "sqlalchemy": "sqlalchemy",
    "python-dotenv": "dotenv",
    "scikit-learn": "sklearn",
    "scipy": "scipy",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "hdbscan": "hdbscan",
}
_PLACEHOLDERS = {"", "your_password_here", "your_real_password", "your_username",
                 "your_user", "change_me", "changeme", "replace_me"}


def _missing_deps() -> list[str]:
    return [pkg for pkg, mod in _REQUIRED_DEPS.items() if importlib.util.find_spec(mod) is None]


def _read_env_file() -> dict[str, str]:
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _is_placeholder(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in _PLACEHOLDERS or text.startswith("your_")


def _db_settings() -> dict[str, Any]:
    env = _read_env_file()

    def value(key: str, default: str = "") -> str:
        return os.environ.get(key) or env.get(key) or default

    port_raw = value("PSQL_PORT", "5432")
    try:
        port: int | None = int(port_raw)
    except ValueError:
        port = None
    return {
        "host": value("PSQL_HOST", "localhost"),
        "port": port,
        "user": value("PSQL_USER"),
        "password": value("PSQL_PASSWORD"),
        "database": value("PSQL_DBNAME", "staging"),
        "env_present": (PROJECT_ROOT / ".env").exists(),
    }


def _db_config_errors(settings: dict[str, Any]) -> list[str]:
    errors = []
    if not settings["port"]:
        errors.append("PSQL_PORT must be a number.")
    for key, label in [("user", "PSQL_USER"), ("password", "PSQL_PASSWORD"), ("database", "PSQL_DBNAME")]:
        if _is_placeholder(settings.get(key)):
            errors.append(f"{label} is missing or still a placeholder.")
    return errors


def _connect_database(settings: dict[str, Any], database: str):
    import psycopg2

    return psycopg2.connect(
        host=settings["host"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        dbname=database,
        connect_timeout=3,
    )


def _database_missing(exc: Exception) -> bool:
    return getattr(exc, "pgcode", None) == "3D000" or "does not exist" in str(exc).lower()


def _create_database(settings: dict[str, Any]) -> str | None:
    from psycopg2 import sql

    last_error = None
    for admin_db in ("postgres", "template1"):
        conn = None
        try:
            conn = _connect_database(settings, admin_db)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings["database"])))
            return None
        except Exception as exc:
            if getattr(exc, "pgcode", None) == "42P04":  # duplicate_database
                return None
            last_error = exc
        finally:
            if conn is not None:
                conn.close()
    return str(last_error or "unknown database creation error")


def _db_status(create_missing: bool = False) -> dict[str, Any]:
    settings = _db_settings()
    db = {
        "configured": False,
        "host": settings["host"],
        "port": settings["port"],
        "database": settings["database"],
        "reachable": False,
        "database_exists": False,
        "created": False,
        "error": None,
    }
    config_errors = _db_config_errors(settings)
    if config_errors:
        db["error"] = " ".join(config_errors)
        return db
    db["configured"] = True

    try:
        with socket.create_connection((settings["host"], settings["port"]), timeout=2):
            db["reachable"] = True
    except Exception as exc:
        db["error"] = f"PostgreSQL is not reachable at {settings['host']}:{settings['port']}: {exc}"
        return db

    if "psycopg2-binary" in _missing_deps():
        db["error"] = f"psycopg2 is not installed. {INSTALL_HINT}"
        return db

    try:
        conn = _connect_database(settings, settings["database"])
        conn.close()
        db["database_exists"] = True
        return db
    except Exception as exc:
        if not _database_missing(exc):
            db["error"] = str(exc)
            return db

    if create_missing:
        err = _create_database(settings)
        if err is None:
            db["created"] = True
            db["database_exists"] = True
            return db
        db["error"] = (f"Database {settings['database']!r} does not exist and could not be created: {err}. "
                       f"Create it manually with `createdb -h {settings['host']} -p {settings['port']} "
                       f"-U {settings['user']} {settings['database']}`.")
    else:
        db["error"] = f"Database {settings['database']!r} does not exist."
    return db


def _preflight_or_error() -> None:
    settings = _db_settings()
    errors = _db_config_errors(settings)
    missing = _missing_deps()
    if missing:
        errors.append(f"Missing Python packages: {', '.join(missing)}. {INSTALL_HINT}")
    if errors:
        raise HTTPException(400, " ".join(errors))
    db = _db_status(create_missing=True)
    if not (db["configured"] and db["reachable"] and db["database_exists"]):
        raise HTTPException(400, db["error"] or "Local PostgreSQL is not ready.")


def _build_command(phase: str, force_dw: bool, skip_val: bool) -> list[str]:
    extra: list[str] = []
    if force_dw:
        extra.append("--force-dw-load")
    if skip_val:
        extra.append("--skip-validation")
    return [sys.executable, "main.py", "--phase", phase, *extra]


# ---- subprocess runner ------------------------------------------------------
def _run_pipeline(run_id: str, phase: str, force_dw: bool, skip_val: bool) -> None:
    """Background thread: run the local Python pipeline and capture stdout."""
    global _current_run_id
    run = _runs[run_id]
    cmd = _build_command(phase, force_dw, skip_val)
    run["command"] = " ".join(cmd)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    except Exception as exc:  # pragma: no cover - env dependent
        run["exit_code"] = -1
        run["error"] = str(exc)
        run["ended_at"] = _now()
        with _lock:
            if _current_run_id == run_id:
                _current_run_id = None
        return

    run["pid"] = proc.pid
    run["proc"] = proc
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            run["lines"].append(line.rstrip("\r\n"))
        proc.wait()
        run["exit_code"] = proc.returncode
    except Exception as exc:  # pragma: no cover
        run["exit_code"] = -1
        run["error"] = str(exc)
    finally:
        run["ended_at"] = _now()
        run["proc"] = None
        with _lock:
            if _current_run_id == run_id:
                _current_run_id = None


# ---- FastAPI app ------------------------------------------------------------
app = FastAPI(title="Pipeline Dashboard API", version="1.0")


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Check local .env, Python deps, and PostgreSQL reachability."""
    missing = _missing_deps()
    db = _db_status(create_missing=False)
    return {"env_present": (PROJECT_ROOT / ".env").exists(), "db": db, "project_root": str(PROJECT_ROOT),
            "python": sys.version.split()[0], "runner": RUNNER,
            "missing_deps": missing, "local_deps_present": not missing}


@app.get("/api/status")
def status() -> dict[str, Any]:
    artifacts = []
    for a in REPORT_ARTIFACTS:
        p = REPORTS_DIR / a["file"]
        artifacts.append({
            "name": a["name"], "file": a["file"], "label": a["label"], "kind": a["kind"],
            "exists": p.exists(),
            "size": p.stat().st_size if p.exists() else 0,
            "mtime": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                     if p.exists() else None,
        })
    active = _active_run()
    active_view = None
    if active:
        active_view = {"run_id": active["run_id"], "phase": active["phase"],
                       "started_at": active["started_at"], "running": active["proc"] is not None,
                       "exit_code": active["exit_code"], "lines": len(active["lines"])}
    return {"artifacts": artifacts, "active_run": active_view,
            "has_results": (REPORTS_DIR / "ml_results.json").exists(),
            "runner": RUNNER}


@app.post("/api/run")
def start_run(body: dict[str, Any]) -> JSONResponse:
    global _current_run_id
    phase = body.get("phase", "all")
    if phase not in VALID_PHASES:
        raise HTTPException(400, f"invalid phase; valid: {VALID_PHASES}")
    with _lock:
        if _current_run_id is not None and _runs.get(_current_run_id, {}).get("proc") is not None:
            raise HTTPException(409, "a pipeline run is already active; stop it first")
    _preflight_or_error()
    with _lock:
        if _current_run_id is not None and _runs.get(_current_run_id, {}).get("proc") is not None:
            raise HTTPException(409, "a pipeline run is already active; stop it first")
        run_id = uuid.uuid4().hex[:12]
        run = {"run_id": run_id, "phase": phase,
               "force_dw_load": bool(body.get("force_dw_load", False)),
               "skip_validation": bool(body.get("skip_validation", False)),
               "started_at": _now(), "ended_at": None,
               "exit_code": None, "error": None, "pid": None,
               "proc": None, "lines": [], "command": None}
        _runs[run_id] = run
        _current_run_id = run_id
    threading.Thread(target=_run_pipeline,
                     args=(run_id, phase, run["force_dw_load"], run["skip_validation"]),
                     daemon=True).start()
    return JSONResponse({"run_id": run_id, "phase": phase, "started_at": run["started_at"]},
                        status_code=202)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {"run_id": run_id, "phase": run["phase"], "started_at": run["started_at"],
            "ended_at": run["ended_at"], "exit_code": run["exit_code"],
            "error": run["error"], "running": run["proc"] is not None,
            "n_lines": len(run["lines"]), "command": run["command"]}


@app.get("/api/logs/{run_id}")
async def stream_logs(run_id: str) -> StreamingResponse:
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, "run not found")

    async def event_gen():
        cursor = 0
        while True:
            n = len(run["lines"])
            if cursor < n:
                for i in range(cursor, n):
                    yield f"data: {json.dumps({'line': run['lines'][i]})}\n\n"
                cursor = n
            if run["proc"] is None and cursor >= len(run["lines"]):
                yield f"event: done\ndata: {json.dumps({'exit_code': run['exit_code'], 'error': run['error']})}\n\n"
                return
            await asyncio.sleep(0.25)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/stop")
def stop_run() -> dict[str, Any]:
    run = _active_run()
    if not run or run["proc"] is None:
        return {"stopped": False, "reason": "no active run"}
    try:
        run["proc"].terminate()
        run["lines"].append(f"[gui] termination requested for pid {run['pid']}")
    except Exception as exc:
        return {"stopped": False, "reason": str(exc)}
    return {"stopped": True, "run_id": run["run_id"]}


@app.get("/api/results")
def results() -> JSONResponse:
    """Reuse DashboardGenerator.build_payload() — same blob the static dashboard uses."""
    try:
        from dashboard_generator import DashboardGenerator
        payload = DashboardGenerator().build_payload()
        return JSONResponse(payload)
    except AssertionError as exc:
        return JSONResponse({"error": f"results incomplete: {exc}",
                             "hint": "Run `--phase all` (or ml-pipeline + ml-report) first.",
                             "generated_at": None, "targets": [], "predictors": [],
                             "provinces": [], "clustering": {}, "regression": {},
                             "spearman": {"matrix": [], "correlations": {}},
                             "province_data": {}, "colors": []}, status_code=200)
    except Exception as exc:
        return JSONResponse({"error": str(exc),
                             "hint": "Is reports/ml_results.json present? Run the pipeline first.",
                             "generated_at": None, "targets": [], "predictors": [],
                             "provinces": [], "clustering": {}, "regression": {},
                             "spearman": {"matrix": [], "correlations": {}},
                             "province_data": {}, "colors": []}, status_code=200)


@app.get("/api/config")
def get_config() -> dict[str, Any]:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception as exc:
        raise HTTPException(500, f"could not read config: {exc}")


@app.post("/api/config")
def save_config(body: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise HTTPException(400, "config must be a JSON object")
    # Light validation to avoid corrupting the pipeline's config.
    cl = body.get("clustering", {})
    km = cl.get("kmeans", {}) if isinstance(cl, dict) else {}
    if isinstance(km, dict):
        mk = km.get("max_k")
        if mk is not None and (not isinstance(mk, int) or mk < 2):
            raise HTTPException(400, "clustering.kmeans.max_k must be an int >= 2")
    fs = body.get("feature_selection", {})
    if isinstance(fs, dict):
        thr = fs.get("correlation_threshold")
        if thr is not None and not (0 <= float(thr) <= 1):
            raise HTTPException(400, "feature_selection.correlation_threshold must be in [0,1]")
    # Atomic write.
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False))
    tmp.replace(CONFIG_PATH)
    return {"saved": True, "path": str(CONFIG_PATH)}


@app.get("/api/reports/{name}")
def get_report(name: str) -> FileResponse:
    art = next((a for a in REPORT_ARTIFACTS if a["name"] == name), None)
    if not art:
        raise HTTPException(404, "unknown report")
    p = REPORTS_DIR / art["file"]
    if not p.exists():
        raise HTTPException(404, "report not generated yet")
    return FileResponse(p, filename=art["file"])


# ---- static + index ---------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
