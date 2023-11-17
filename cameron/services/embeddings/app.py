import asyncio
import contextlib
from typing import List

from sentence_transformers import SentenceTransformer
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

EMBEDDINGS_MODEL_NAME = "intfloat/multilingual-e5-large"
EMBEDDINGS_ENCODING_PREFIX = "query: "


class EmbeddingsService:
    def __init__(self):
        self.lock = asyncio.Lock()
        print(f'embeddings: loading sentence transformer')
        self.model = SentenceTransformer(EMBEDDINGS_MODEL_NAME)
        print(f'embeddings: ready')

    async def encode(self, input_texts: List[str]) -> List[List[float]]:
        async with self.lock:
            output = self.model.encode([
                EMBEDDINGS_ENCODING_PREFIX + input_text for input_text in input_texts
            ], normalize_embeddings=True)
            return [
                t.tolist() for t in output
            ]

    def destroy(self):
        self.model = None


async def route_invoke(req: Request):
    text = (await req.json())['text']
    output = await req.state.service.encode([text])
    return JSONResponse({
        'vector': output[0]
    })


@contextlib.asynccontextmanager
async def lifespan(app):
    service = EmbeddingsService()
    yield dict(service=service)
    service.destroy()


app = Starlette(
    routes=[
        Route('/embeddings/encode', endpoint=route_invoke, methods=['POST', 'GET'])
    ],
    lifespan=lifespan
)
