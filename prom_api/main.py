
import json
import logging
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from threading import Lock

from fastapi import FastAPI, Request, Query
from fastapi.responses import Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI()
START_TIME = time.monotonic()

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

logs = deque(maxlen=2000)
logs_lock = Lock()

logger = logging.getLogger("requests_json")
logger.setLevel(logging.INFO)
logger.propagate = False
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.handlers.clear()
logger.addHandler(handler)


@app.middleware("http")
async def track_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    started = time.time()
    status = 500

    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        entry = {
            "level": "INFO" if status < 500 else "ERROR",
            "ts": datetime.fromtimestamp(
                started, timezone.utc
            ).isoformat(),
            "path": request.url.path,
            "request_id": request_id,
            "method": request.method,
            "status": status,
            "duration_ms": round((time.time() - started) * 1000, 3),
        }

        REQUESTS.labels(request.method, request.url.path, str(status)).inc()

        with logs_lock:
            logs.append(entry)

        logger.info(json.dumps(entry))


@app.get("/work")
async def work(n: int = Query(default=1, ge=0, le=1000000)):
    # Perform n simple units of work.
    sum(range(n))
    return {
        "email": os.getenv("SERVICE_EMAIL", "service@example.com"),
        "done": n,
    }


@app.get("/metrics")
async def metrics():
    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "uptime_s": float(max(0, time.monotonic() - START_TIME)),
    }


@app.get("/logs/tail")
async def logs_tail(
    limit: int = Query(default=100, ge=1, le=2000)
):
    with logs_lock:
        return list(logs)[-limit:]
