import asyncio
import contextlib

from typing import List
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from transformers import AutoTokenizer, AutoModelForCausalLM

MODEL_NAME = "Qwen/Qwen-7B-Chat-Int4"


class GenerationService:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME, trust_remote_code=True)

        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            device_map="auto",
            trust_remote_code=True
        ).eval()

    def generate(self, input_text: str, history=List[List[str]], **kwargs) -> str:
        output_text, history = self.model.chat(
            self.tokenizer,
            input_text,
            history
        )
        return output_text, history

    def destroy(self):
        self.tokenizer = None
        self.model = None


async def route_generate(req: Request):
    data = await req.json()
    output_text, history = req.state.service.generate(**data)
    return JSONResponse(dict(output_text=output_text, history=history))


@contextlib.asynccontextmanager
async def lifespan(app):
    service = GenerationService()
    yield dict(service=service)
    service.destroy()


app = Starlette(
    routes=[
        Route('/generation/generate',
              endpoint=route_generate, methods=['POST'])
    ],
    lifespan=lifespan
)
