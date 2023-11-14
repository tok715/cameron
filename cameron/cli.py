import contextlib
from typing import AsyncIterator

import click
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route

from .routes import route_index
from .state import State


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[State]:
    yield {}


app = Starlette(
    routes=[
        Route('/', route_index),
    ],
    lifespan=lifespan,
)


@click.command()
@click.option("--port", "-p", "opt_port", default=5000, type=int)
@click.option("--host", "-h", "opt_host", default="127.0.0.1", type=str)
def cli(opt_port: int, opt_host: str):
    uvicorn.run("cameron.cli:app", host=opt_host, port=opt_port, log_level="info")


if __name__ == '__main__':
    cli()
