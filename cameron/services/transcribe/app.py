import asyncio
import contextlib
import json
import os.path
import time
from typing import Optional

from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.routing import WebSocketRoute
from starlette.types import Scope, Receive, Send
from starlette.websockets import WebSocket

from cameron.vendor import nls


def get_aliyun_nls_token() -> str:
    token_file = os.path.join('data', 'aliyun-nls.token.json')

    conf = {}

    if os.path.exists(token_file):
        # noinspection PyBroadException
        try:
            with open(token_file, 'r') as f:
                conf = json.load(f)
        except Exception:
            pass

    if 'expires_at' in conf and 'token' in conf:
        if conf['expires_at'] > int(time.time()):
            print('aliyun-nls: using existed token')
            return conf['token']

    token, expires_at = nls.get_token(
        os.getenv('ALIYUN_NLS_ACCESS_KEY_ID'),
        os.getenv('ALIYUN_NLS_ACCESS_KEY_SECRET'),
    )

    print('aliyun-nls: fetched new token')

    with open(token_file, 'w') as f:
        json.dump({
            'token': token,
            'expires_at': expires_at,
        }, f)

    return token


def decode_aliyun_nls_data(s: str) -> (str, int):
    data = json.loads(s)
    if "payload" not in data:
        return "", 0
    payload = data["payload"]
    if "result" not in payload or "index" not in payload:
        return "", 0
    return payload["result"], payload["index"]


class RecognizerEndpoint(WebSocketEndpoint):
    encoding = 'bytes'

    def __init__(self, scope: Scope, receive: Receive, send: Send):
        super().__init__(scope, receive, send)
        self.transcriber: Optional[nls.NlsSpeechTranscriber] = None

    async def on_connect(self, websocket: WebSocket) -> None:
        await super().on_connect(websocket)

        def on_sentence_end(s: str, *args, **kwargs):
            content, index = decode_aliyun_nls_data(s)
            if not content or not index:
                return
            print(f"on_sentence_end: {content}")
            asyncio.run(websocket.send_text(content))

        def on_result_changed(s: str, *args, **kwargs):
            result, index = decode_aliyun_nls_data(s)
            if not result or not index:
                return
            print(f"on_result_changed: {result}")

        def on_close(*args, **kwargs):
            async def try_close():
                try:
                    await websocket.close()
                except Exception as _:
                    pass

            asyncio.run(try_close())

        nls_token = get_aliyun_nls_token()
        self.transcriber = nls.NlsSpeechTranscriber(
            url=os.getenv('ALIYUN_NLS_ENDPOINT'),
            token=nls_token,
            appkey=os.getenv('ALIYUN_NLS_APP_KEY'),
            on_sentence_end=on_sentence_end,
            on_result_changed=on_result_changed,
            on_close=on_close,
        )
        self.transcriber.start(
            aformat="pcm",
            sample_rate=16000,
            ch=1,
            enable_intermediate_result=True,
            enable_punctuation_prediction=True,
            enable_inverse_text_normalization=True,
        )

    async def on_receive(self, websocket: WebSocket, data: bytes) -> None:
        await super().on_receive(websocket, data)
        self.transcriber.send_audio(data)

    async def on_disconnect(self, websocket: WebSocket, close_code: int) -> None:
        if self.transcriber:
            self.transcriber.stop()
        await super().on_disconnect(websocket, close_code)


class RecognizerService:
    def __init__(self):
        self.lock = asyncio.Lock()

    def destroy(self):
        pass


@contextlib.asynccontextmanager
async def lifespan(app):
    service = RecognizerService()
    yield dict(service=service)
    service.destroy()


app = Starlette(
    routes=[
        WebSocketRoute('/transcribe/ws', endpoint=RecognizerEndpoint)
    ],
    lifespan=lifespan
)
