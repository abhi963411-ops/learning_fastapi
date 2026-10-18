
import asyncio
import base64
import json
import math
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Orders API", version="1.0.0")

# Your assigned values
TOTAL_ORDERS = 57
RATE_LIMIT = 15
WINDOW_SECONDS = 10

# Allow browser-based grading from any origin.
app = CORSMiddleware(
    app,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)


# Fixed catalog: IDs 1 through 57
CATALOG = [
    {"id": i, "product": f"Product {i}", "quantity": 1}
    for i in range(1, TOTAL_ORDERS + 1)
]

# In-memory state (suitable for a single running instance)
idempotency_store: dict[str, dict[str, Any]] = {}
created_orders: dict[str, dict[str, Any]] = {}
next_created_id = 1
idempotency_lock = asyncio.Lock()

# Each client has its own rolling 10-second window.
client_requests = defaultdict(deque)
rate_limit_lock = asyncio.Lock()


class OrderRequest(BaseModel):
    product: str = "Default Product"
    quantity: int = Field(default=1, ge=1)
    details: dict[str, Any] = Field(default_factory=dict)


@app.middleware("http")
async def per_client_rate_limit(request: Request, call_next):
    # Let CORS preflight requests through without consuming the quota.
    if request.method == "OPTIONS":
        return await call_next(request)

    client_id = request.headers.get("X-Client-Id", "anonymous")
    now = time.monotonic()

    async with rate_limit_lock:
        timestamps = client_requests[client_id]

        # Remove requests outside the rolling 10-second window.
        while timestamps and now - timestamps[0] >= WINDOW_SECONDS:
            timestamps.popleft()

        if len(timestamps) >= RATE_LIMIT:
            retry_after = max(
                1, math.ceil(WINDOW_SECONDS - (now - timestamps[0]))
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        timestamps.append(now)

    return await call_next(request)


@app.get("/")
async def root():
    return {
        "service": "Orders API",
        "total_orders": TOTAL_ORDERS,
        "rate_limit": RATE_LIMIT,
        "window_seconds": WINDOW_SECONDS,
    }


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/orders", status_code=201)
async def create_order(
    body: OrderRequest | None = None,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key"
    ),
):
    global next_created_id

    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Idempotency-Key header is required",
        )

    async with idempotency_lock:
        # Return the original order for a repeated key.
        if idempotency_key in idempotency_store:
            return idempotency_store[idempotency_key]

        payload = body or OrderRequest()

        order = {
            "id": f"created-{next_created_id}",
            "product": payload.product,
            "quantity": payload.quantity,
            "details": payload.details,
        }
        next_created_id += 1

        idempotency_store[idempotency_key] = order
        created_orders[order["id"]] = order

        # Return 201 for the first request.
        return JSONResponse(status_code=201, content=order)


@app.get("/orders")
async def list_orders(
    limit: int = Query(default=10, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    # A cursor represents the next zero-based catalog position.
    if cursor is None:
        start = 0
    else:
        try:
            decoded = base64.urlsafe_b64decode(
                cursor.encode("ascii") + b"=" * (-len(cursor) % 4)
            )
            start = int(decoded.decode("ascii"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

        if start < 0 or start > TOTAL_ORDERS:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    end = min(start + limit, TOTAL_ORDERS)
    items = CATALOG[start:end]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = base64.urlsafe_b64encode(
            str(end).encode("ascii")
        ).decode("ascii").rstrip("=")

    return {
        "items": items,
        "next_cursor": next_cursor,
    }
