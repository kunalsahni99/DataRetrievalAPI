import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.session import create_db_and_tables
from app.routers import licenses, sync, users, auth

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="M365 Data API",
    description=(
        "Fetches Microsoft 365 tenant data from Graph API and persists it "
        "for consumption by the LangGraph agent pipeline. "
        "Agents read from this API — they never call Graph directly."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(sync.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(licenses.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}