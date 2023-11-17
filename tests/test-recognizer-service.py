import asyncio
from pathlib import Path

import websockets


async def main():
    sample_path = str(Path(__file__).parent.parent / 'data' / 'tts_ref.pcm')
    socket_path = str(Path(__file__).parent.parent / 'data' / 'service-transcribe.socket')

    async def print_ws_text(ws):
        while True:
            text = await ws.recv()
            print(f'{text}')

    async with websockets.unix_connect(socket_path, 'ws://localhost/transcribe/ws') as ws:
        task = asyncio.create_task(print_ws_text(ws))
        with open(sample_path, 'rb') as f:
            # read with buffer 1k
            while True:
                data = f.read(1024)
                if not data:
                    break
                await ws.send(data)
        asyncio.sleep(5)
        ws.close()
        await task


if __name__ == "__main__":
    asyncio.run(main())
