import asyncio
import logging
import traceback
from server.engine.app import ServerApp
from server.core.state import EntryState
from server.core import packet
from server.core.database import model
from ssl import SSLContext, PROTOCOL_TLS_SERVER

def get_ssl_context(certpath: str, keypath: str) -> SSLContext:
    logging.info("Loading encryption key")
    ssl_context: SSLContext = SSLContext(PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain(certpath, keypath)
    except FileNotFoundError:
        raise FileNotFoundError(f"No encryption key or certificate found. Please generate a pair and save them to {certpath} and {keypath}")

    return ssl_context

async def main() -> None:
    logging.info("Starting server")

    ssl_context: SSLContext = get_ssl_context("server/core/app/ssl/localhost.crt", "server/core/app/ssl/localhost.key")
    server_app: ServerApp = ServerApp("localhost", 443, ssl_context=ssl_context)

    server_app.register_packets(packet)
    server_app.register_db_models(model)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(server_app.start(initial_state=EntryState))
        tg.create_task(server_app.run(ticks_per_second=10))


    logging.info("Server stopped")


if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO)
    
    # Silence SQLAlchemy logging
    sqlalchemy_engine_logger = logging.getLogger('sqlalchemy.engine')
    sqlalchemy_engine_logger.setLevel(logging.WARNING)


    # Set format for logging
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        traceback.print_exc() 