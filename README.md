# Netbound
A safe and fair way to play games with friends over the internet

## ⚡ Quick start
The following is a basic example of how to start a websockets game server using Netbound. This example uses the `asyncio` library to run the server in a non-blocking manner.

```python
# File: __main__.py

import asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from netbound.app import ServerApp

async def main() -> None:
    db_engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///database.sqlite3")
    server_app: ServerApp = ServerApp("localhost", 443, db_engine)

    print("Server starting...")

    async with asyncio.TaskGroup() as tg:
        tg.create_task(server_app.start())
        tg.create_task(server_app.run(ticks_per_second=10))

    print("Server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user")
```

## Defining packets
Packets are the primary way of communicating between the server and the client, or between server "protocols". Create your own module(s) with subclass packets of `netbound.packet.BasePacket` and inject them into the server app.

```python
# File: example_packets.py

from netbound.packet import BasePacket

class ExamplePacket(BasePacket):
    my_field: str
    my_other_field: int

class AnotherPacket(BasePacket):
    some_field: list[int]
```

```python
# File: __main__.py

import example_packets
from netbound.app import ServerApp

server_app: ServerApp = ServerApp("localhost", 443)
server_app.register_packets(example_packets)
```

## Defining models
Models are the primary way of storing data in the database. Create your own module(s) with subclassed models of `sqlalchemy.orm.DeclarativeBase` and inject them into the server app.

```python
# File: example_models.py

from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class ExampleModel(Base):
    my_field: str
    my_other_field: int
```

Now we need to tell `alembic` where your models are located:
```shell
alembic init alembic
```

And edit the `alembic/env.py` file to point to your models' `Base` class so that when when you run the following shell commands,
```shell
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```
you will see your database file appear with all of your models inside.

For more information, see https://alembic.sqlalchemy.org/en/latest/tutorial.html.

## Defining states
States are the primary way of managing the game state. Create an initial state for the server app and tell it to use that state.

```python
# File: entry_state.py

from netbound.state import BaseState
from example_packets import ExamplePacket, AnotherPacket
from example_models import ExampleModel

class EntryState:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._name: str = "entry_state"

    async def _on_transition(self, *args, **kwargs) -> None:
        await self._queue_local_client_send(ExamplePacket(from_pid=self._pid, my_field="hello", my_other_field=42))

        async with self._get_db_session() as session:
            eg: ExampleModel = ExampleModel(my_field="hello", my_other_field=42)
            session.add(eg)
            session.commit()

    async def handle_anotherpacket(self, p: AnotherPacket) -> None:
        print("Received another packet with fields:")
        for n in p.some_field:
            print(n)
```

```python
# File: __main__.py

import asyncio
from entry_state import EntryState
from netbound.app import ServerApp

async def main() -> None:
    server_app: ServerApp = ServerApp("localhost", 443)

    print("Server starting...")

    async with asyncio.TaskGroup() as tg:
        tg.create_task(server_app.start(initial_state=EntryState))
        tg.create_task(server_app.run(ticks_per_second=10))

    print("Server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Server stopped by user")
```

# NPCs
NPCs can be treated as just a special type of player protocol which doesn't have a client. This is exactly how Netbound treats them.

You can add NPCs to your game by first creating a state for them to live in. It can be easy to subclass some sort of `PlayState` you might have for your players, but 
remember not to use the `self._queue_local_client_send` method. Instead, it is safest to simply override that function to log a warning in the `__init__` method of your NPC state.

NPC states are also where `netbound.schedule` really shines, as it is a non-blocking way to schedule events in the future. This is useful for making NPCs move around, or do other things at certain times.

```python
# File: npc_state.py
from netbound import schedule
from server.packet import ChatPacket
from netbound.constants import EVERYONE
from server.state import LoggedState

class BobPlayState(LoggedState):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._queue_local_client_send = lambda p: self._logger.warning(f"NPC tried to send packet to client: {p}")

    async def handle_chat(self, p: ChatPacket) -> None:
        reply: str = "Hi, I'm Bob!"
        schedule(
            1, 
            lambda: self._queue_local_protos_send(ChatPacket(from_pid=self._pid, to_pid=EVERYONE, exclude_sender=True, message=reply))
        )
```

Then, in your main file, you can add the NPC to the server app like so:

```python
# File: __main__.py
from server.npc_state import BobPlayState

# ... (regular setup code)
server_app.add_npc(BobPlayState)
# ...
```

This will add an NPC to the server app that will reply to any chat messages with "Hi, I'm Bob!" after 1 second.