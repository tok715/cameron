import click
import uvicorn

from cameron.services import services_running


@click.command()
@click.option("--port", "-p", "opt_port", default=8000, type=int)
@click.option("--host", "-h", "opt_host", default="0.0.0.0", type=str)
def cli(opt_port: int, opt_host: str):
    with services_running():
        uvicorn.run("cameron:app", host=opt_host, port=opt_port, log_level="info")


if __name__ == '__main__':
    cli()
