
import time
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

ALLOWED_ORIGIN = "https://dash-xpnjys.example.com"
EMAIL = "22f3003081@ds.study.iitm.ac.in"

# Allow only the assigned origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Added after CORS so this middleware also sees preflight responses.
@app.middleware("http")
async def add_required_headers(request, call_next):
    start_time = time.perf_counter()
    request_id = str(uuid.uuid4())

    response = await call_next(request)

    elapsed = time.perf_counter() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{elapsed:.6f}"

    return response


@app.get("/stats")
async def get_stats(values: str = Query(...)):
    try:
        numbers = [int(value.strip()) for value in values.split(",")]
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="values must be comma-separated integers",
        )

    if not numbers:
        raise HTTPException(status_code=422, detail="At least one integer is required")

    total = sum(numbers)
    count = len(numbers)

    return {
        "email": EMAIL,
        "count": count,
        "sum": total,
        "min": min(numbers),
        "max": max(numbers),
        "mean": total / count,
    }
