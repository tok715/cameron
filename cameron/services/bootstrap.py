import multiprocessing
import os

import uvicorn

SERVICE_NAMES = [
    'embeddings',
    'generation',
    'synthesize',
    'transcribe',
]


def get_service_socket_path(name: str) -> str:
    return os.path.join('data', 'service-' + name + ".socket")


def run_service(name: str):
    socket_path = get_service_socket_path(name)
    if os.path.exists(socket_path):
        os.remove(socket_path)

    uvicorn.run(f'cameron.services.{name}:app', uds=socket_path, log_level="info")


class services_running:
    def __init__(self):
        self.processes = [
            multiprocessing.Process(
                target=run_service,
                args=(name,)
            )
            for name in SERVICE_NAMES
        ]

    def __enter__(self):
        for process in self.processes:
            process.start()

    def __exit__(self, *args, **kwargs):
        for process in self.processes:
            process.join()
