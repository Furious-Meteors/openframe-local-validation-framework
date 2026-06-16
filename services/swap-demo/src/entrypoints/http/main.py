from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from bootstrap.dependencies import close_backends, init_backends
from entrypoints.http.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_backends()
    yield
    await close_backends()


app = FastAPI(title="swap-demo", lifespan=lifespan)
app.include_router(router)
