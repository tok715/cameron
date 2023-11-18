import asyncio
import contextlib
import os.path
import time
from pathlib import Path
from typing import Optional, Set, List
import json

import anyio
from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import Scope, Receive, Send
from starlette.websockets import WebSocket

from cameron.services import ServiceWebSocketClient, ServiceWebSocketClientDelegate, invoke_service

DIR_ASSETS = Path(__file__).parent / 'assets'
DIR_WEB_STATIC = DIR_ASSETS / 'web' / 'static' / 'dist'
DIR_WEB_TEMPLATES = DIR_ASSETS / 'web' / 'templates'

TEMPLATES = Jinja2Templates(directory=DIR_WEB_TEMPLATES)


class HistoryManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._path = os.path.join('data', 'history.json')
        self._data = []
        if os.path.exists(self._path):
            with open(self._path, 'r') as f:
                self._data = json.load(f)

    def get(self) -> List[List[str]]:
        return self._data

    async def set(self, data=List[List[str]]):
        async with self._lock:
            self._data = data
            await self._save()

    async def append_user(self, s: str):
        async with self._lock:
            # no history, or last item already has a bot response
            if not self._data or self._data[-1][1]:
                item = ['', '']
                self._data.append(item)
            else:
                item = self._data[-1]

            item[0] = item[0]+s

            await self._save()

    async def append_bot(self, s: str):
        async with self._lock:
            if not self._data:
                return

            # just append last item's bot response
            self._data[-1][1] = self.data[-1][1]+s

            await self._save()

    async def _save(self):
        data = json.dumps(self._data, ensure_ascii=False)
        async with await anyio.open_file(self._path, 'w') as f:
            await f.write(data)

    async def save(self):
        async with self._lock:
            await self._save()


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    history = HistoryManager()
    yield {'history': history}


async def route_index(request):
    return TEMPLATES.TemplateResponse(request, 'index.html', context={
        "now": time.time()
    })


KIND_VOICE_INPUT = 0x01
KIND_VOICE_TRANSCRIBE_RESULT = 0x02
KIND_VOICE_SYNTHESIZE_RESULT = 0x03
KIND_MODEL_GENERATE_RESULT = 0x04

CONNECTIONS: Set['CameronEndpoint'] = set()


async def broadcast_frame(kind: int, data: bytes | str):
    if isinstance(data, str):
        data = data.encode('utf-8')
    for endpoint in CONNECTIONS:
        try:
            await endpoint.websocket.send_bytes(bytes([kind]) + data)
        except Exception as e:
            print(f'broadcast_frame failed: {e}')


class CameronEndpoint(WebSocketEndpoint, ServiceWebSocketClientDelegate):
    encoding = 'bytes'

    def __init__(self, scope: Scope, receive: Receive, send: Send):
        super().__init__(scope, receive, send)
        self.websocket: Optional[WebSocket] = None
        self.transcribe: Optional[ServiceWebSocketClient] = None
        self.synthesize: Optional[ServiceWebSocketClient] = None
        self.history: Optional[HistoryManager] = None
        self.psyche_loop_task = None

    async def psyche_loop(self):
        while self.websocket:
            await asyncio.sleep(5)

            if not self.websocket:
                return

            history = self.history.get()

            # if last history has a bot reponse
            if history and history[-1][1]:
                continue

            try:
                response = await invoke_service(
                    'generation',
                    '/generation/generate',
                    input_text=history[-1][0],
                    history=history[:-1],
                    max_new_tokens=64,
                )
                print(f'generation response: {response}')
                output_text = response['output_text']
                history = response['history']
                await self.synthesize.send(output_text)
                await self.history.set(history)
                await broadcast_frame(KIND_MODEL_GENERATE_RESULT, output_text)
            except Exception as e:
                print(f'psyche_loop failed: {e}')

    async def on_connect(self, websocket: WebSocket) -> None:
        await super().on_connect(websocket)

        self.history = websocket.state.history
        self.websocket = websocket

        self.transcribe = ServiceWebSocketClient(
            'transcribe',
            '/transcribe/ws',
            self,
        )
        self.synthesize = ServiceWebSocketClient(
            'synthesize',
            '/synthesize/ws',
            self,
        )

        CONNECTIONS.add(self)

        self.psyche_loop_task = asyncio.create_task(self.psyche_loop())

    async def on_receive(self, websocket: WebSocket, data: bytes) -> None:
        await super().on_receive(websocket, data)

        if data[0] == KIND_VOICE_INPUT:
            await self.transcribe.send(data[1:])

    async def on_service_receive(self, service_name: str, service_path: str, data: str | bytes):
        if service_name == 'transcribe':
            if isinstance(data, str):
                await self.history.append_user(data)
                await broadcast_frame(KIND_VOICE_TRANSCRIBE_RESULT, data)

        if service_name == 'synthesize':
            if isinstance(data, bytes):
                await broadcast_frame(KIND_VOICE_SYNTHESIZE_RESULT, data)

    async def on_disconnect(self, websocket: WebSocket, close_code: int) -> None:
        CONNECTIONS.remove(self)

        await self.transcribe.close()
        await self.synthesize.close()

        self.websocket = None

        await self.psyche_loop_task

        await super().on_disconnect(websocket, close_code)


app = Starlette(
    routes=[
        Route('/', endpoint=route_index, methods=['GET']),
        Mount('/static/dist', app=StaticFiles(directory=DIR_WEB_STATIC)),
        WebSocketRoute('/ws', endpoint=CameronEndpoint)
    ],
    lifespan=lifespan,
)
