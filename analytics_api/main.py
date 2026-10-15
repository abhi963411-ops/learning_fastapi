
import os
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


app = FastAPI(title="Analytics API")

# Allow the browser-based grader to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

API_KEY = os.environ.get("API_KEY", "")
EMAIL = os.environ.get("EMAIL", "")


class Event(BaseModel):
    user: str
    amount: float
    ts: int


class AnalyticsRequest(BaseModel):
    events: list[Event]


@app.get("/")
def health_check():
    return {"status": "ok", "service": "analytics-api"}


@app.post("/analytics")
def analytics(
    request: AnalyticsRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    # 1. Authenticate the request.
    if not API_KEY or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not EMAIL:
        raise HTTPException(
            status_code=500,
            detail="Server email is not configured",
        )

    # 2. Calculate aggregates from this request's events.
    positive_totals = defaultdict(float)
    revenue = 0.0

    for event in request.events:
        if event.amount > 0:
            revenue += event.amount
            positive_totals[event.user] += event.amount

    # 3. Find the user with the highest positive-amount total.
    top_user = (
        max(positive_totals, key=positive_totals.get)
        if positive_totals
        else ""
    )

    # 4. Return the required fields.
    return {
        "email": EMAIL,
        "total_events": len(request.events),
        "unique_users": len({event.user for event in request.events}),
        "revenue": revenue,
        "top_user": top_user,
    }
