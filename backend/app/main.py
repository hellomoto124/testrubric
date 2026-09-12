import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from .database import current_rubric as load_current_rubric, initialize


RUBRIC = json.loads((Path(__file__).parent / "data" / "future_9.json").read_text(encoding="utf-8"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize(RUBRIC)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/rubrics/current")
def current_rubric() -> dict:
    return load_current_rubric()
