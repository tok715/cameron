import asyncio
import contextlib
from pathlib import Path
from typing import Optional

from starlette.applications import Starlette
from starlette.endpoints import WebSocketEndpoint
from starlette.routing import Route, WebSocketRoute, Mount
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.types import Scope, Receive, Send
from starlette.websockets import WebSocket
from websockets import WebSocketClientProtocol

from cameron.services import connect_service_websocket

DIR_ASSETS = Path(__file__).parent / 'assets'
DIR_WEB_STATIC = DIR_ASSETS / 'web' / 'static' / 'dist'
DIR_WEB_TEMPLATES = DIR_ASSETS / 'web' / 'templates'

TEMPLATES = Jinja2Templates(directory=DIR_WEB_TEMPLATES)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette):
    yield {}


async def route_index(request):
    return TEMPLATES.TemplateResponse(request, 'index.html')


CONNECTIONS = set()

KIND_VOICE_INPUT = 0x01
KIND_VOICE_TRANSCRIBE_RESULT = 0x02


class CameronEndpoint(WebSocketEndpoint):
    encoding = 'bytes'

    def __init__(self, scope: Scope, receive: Receive, send: Send):
        super().__init__(scope, receive, send)
        self.websocket: Optional[WebSocket] = None
        self.ws_transcribe: Optional[WebSocketClientProtocol] = None

    async def on_connect(self, websocket: WebSocket) -> None:
        await super().on_connect(websocket)

        self.websocket = websocket
        CONNECTIONS.add(websocket)

        self.ws_transcribe = await connect_service_websocket('transcribe', '/transcribe/ws')

        async def handle_ws_transcribe():
            while self.ws_transcribe and self.ws_transcribe.open:
                try:
                    data = await self.ws_transcribe.recv()
                except Exception as e:
                    print(f'ws_transcribe failed: {e}')
                    break
                if isinstance(data, str):
                    print(f'ws_transcribe: {data}')
                    await self.websocket.send_bytes(
                        bytes([KIND_VOICE_TRANSCRIBE_RESULT]) + data.encode('utf-8')
                    )

        asyncio.create_task(handle_ws_transcribe())

    async def on_receive(self, websocket: WebSocket, data: bytes) -> None:
        await super().on_receive(websocket, data)

        if data[0] == KIND_VOICE_INPUT:
            await self.ws_transcribe.send(data[1:])

    async def on_disconnect(self, websocket: WebSocket, close_code: int) -> None:
        await self.ws_transcribe.close()
        self.ws_transcribe = None
        CONNECTIONS.remove(websocket)
        self.websocket = None

        await super().on_disconnect(websocket, close_code)


app = Starlette(
    routes=[
        Route('/', endpoint=route_index, methods=['GET']),
        Mount('/static/dist', app=StaticFiles(directory=DIR_WEB_STATIC)),
        WebSocketRoute('/ws', endpoint=CameronEndpoint)
    ],
    lifespan=lifespan,
)
