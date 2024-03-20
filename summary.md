# `server/__main__.py`
```python
import asyncio
import logging
import traceback
from server.engine.app import ServerApp
from server.core.state import EntryState
from server.core import packet
from server.core.database import model

async def main() -> None:
    logging.info("Starting server")

    server_app: ServerApp = ServerApp("localhost", 443, 10)

    server_app.register_packets(packet)
    server_app.register_db_models(model)

    async with asyncio.TaskGroup() as tg:
        tg.create_task(server_app.start(EntryState))
        tg.create_task(server_app.run())


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
```


