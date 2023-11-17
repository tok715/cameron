import websockets
from websockets import WebSocketClientProtocol

from .bootstrap import get_service_socket_path


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
