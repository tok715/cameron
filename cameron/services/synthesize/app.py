import asyncio
import contextlib
import io
import os
from pathlib import Path
from typing import AsyncIterable

import torch
import torchaudio
from TTS.api import TTS
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from TTS.utils.manage import ModelManager
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket
from torch import Tensor

TTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
TTS_MODEL_SAMPLE_RATE = 24000


class SynthesizeService:
    def __init__(self):
        self.lock = asyncio.Lock()

        def no_check(*args, **kwargs):
            pass

        manager = ModelManager(models_file=TTS.get_models_file_path(), progress_bar=True, verbose=False)
        # patch the manager to skip the config check
        manager.check_if_configs_are_equal = no_check
        model_path, _, _ = manager.download_model(TTS_MODEL_NAME)

        print("synthesize: loading model")
        config = XttsConfig()
        config.load_json(os.path.join(model_path, 'config.json'))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_dir=model_path)
        if torch.cuda.is_available():
            model.cuda()
        self.model = model

        print("synthesize: loading speaker reference")
        self.gpt_cond_latent, self.speaker_embedding = model.get_conditioning_latents(
            audio_path=[str(Path("data") / 'tts_ref.wav')]
        )
        print('synthesize: ready')

    def destroy(self):
        self.model = None
        self.gpt_cond_latent = None
        self.speaker_embedding = None

    # noinspection PyUnresolvedReferences
    @staticmethod
    def encode_wav(data: Tensor, *args, **kwargs) -> bytes:
        buf = io.BytesIO()
        torchaudio.save(buf, data, *args, **kwargs)
        buf.seek(0)
        return buf.read()

    async def inference_stream(self, text: str, **kwargs) -> AsyncIterable[bytes]:
        async with self.lock:
            chunks = self.model.inference_stream(
                text,
                "zh",
                self.gpt_cond_latent,
                self.speaker_embedding,
                **kwargs
            )
            for chunk in chunks:
                data = self.encode_wav(
                    chunk.squeeze().unsqueeze(0).cpu(),
                    sample_rate=TTS_MODEL_SAMPLE_RATE,
                    format='wav'
                )
                yield data


class SynthesizeEndpoint(WebSocketEndpoint):
    encoding = 'text'

    async def on_receive(self, websocket: WebSocket, data: str) -> None:
        await super().on_receive(websocket, data)

        async for wav_data in websocket.state.service.inference_stream(data):
            try:
                await websocket.send_bytes(wav_data)
            except Exception as e:
                print("synthesize: websocket closed", e)
                break


@contextlib.asynccontextmanager
async def lifespan(app):
    service = SynthesizeService()
    yield dict(service=service)
    service.destroy()


app = Starlette(
    routes=[
        WebSocketRoute('/synthesize/ws', endpoint=SynthesizeEndpoint)
    ],
    lifespan=lifespan
)
