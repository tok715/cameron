import asyncio
from typing import Optional, Dict

import httpx
import websockets
from websockets import WebSocketClientProtocol

from .bootstrap import get_service_socket_path


async def invoke_service(name: str, path: str, **kwargs) -> Dict:
    async with httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(
                uds=get_service_socket_path(name),
            ),
            timeout=None,
    ) as client:
        res = await client.post(
            'http://dummyhost' + path,
            json=kwargs,
        )
        return res.json()


async def connect_service_websocket(name: str, path: str) -> WebSocketClientProtocol:
    """
    :param name: service name
    :param path: service url path
    :return:
    """
    if not path.startswith('/'):
        path = '/' + path
    socket_path = get_service_socket_path(name)
    return await websockets.unix_connect(socket_path, 'ws://dummyhost' + path)


class ServiceWebSocketClientDelegate:

    async def on_service_receive(self, service_name: str, service_path: str, data: str | bytes):
        pass


class ServiceWebSocketClient:
    def __init__(self, service_name: str, service_path: str, delegate: ServiceWebSocketClientDelegate):
        self.delegate = delegate
        self.service_name = service_name
        self.service_path = service_path
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.websocket_task: Optional[asyncio.Task] = None
        asyncio.create_task(self._connect())

    async def send(self, data: str | bytes):
        if self.websocket and self.websocket.open:
            try:
                await self.websocket.send(data)
            except Exception as e:
                print(
                    f'websocket send {self.service_name}@{self.service_path} failed: {e}')
                await self.websocket.close()

    async def _handle(self):
        while self.delegate and self.websocket:
            try:
                data = await self.websocket.recv()
            except Exception as e:
                print(
                    f'websocket recv {self.service_name}@{self.service_path} failed: {e}')
                await self.websocket.close()
                break
            if self.delegate:
                await self.delegate.on_service_receive(self.service_name, self.service_path, data)
        if self.delegate:
            print(
                f'websocket closed {self.service_name}@{self.service_path}, reconnecting')
            await asyncio.sleep(3)
            await self._connect()

    async def _connect(self):
        self.websocket = await connect_service_websocket(self.service_name, self.service_path)
        self.websocket_task = asyncio.create_task(self._handle())

    async def close(self):
        self.delegate = None

        if self.websocket:
            await self.websocket.close()
        if self.websocket_task:
            await self.websocket_task

        self.websocket = None
        self.websocket_task = None
