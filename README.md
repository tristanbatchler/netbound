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
        await self._send_to_client(ExamplePacket(from_pid=self._pid, my_field="hello", my_other_field=42))

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
remember not to use the `self._send_to_client` method. Instead, it is safest to simply override that function to log a warning in the `__init__` method of your NPC state.

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
        self._send_to_client = self._dummy_send_to_client

    async def _dummy_send_to_client(self, p: BasePacket) -> None:
        logging.warning(f"NPC {self._name} tried to send a packet to its non-existant client: {p}")

    async def handle_chat(self, p: ChatPacket) -> None:
        reply: str = "Hi, I'm Bob!"
        schedule(
            1, 
            lambda: self._send_to_other(ChatPacket(from_pid=self._pid, to_pid=EVERYONE, exclude_sender=True, message=reply))
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

# Game objects
Sometimes the server needs to keep track of objects in the game that aren't necessarily players, NPCs or models belonging to the database. 
For example, you might want to keep track of the positions of all the bullets in a shooter game. This is where game objects come in.

Instead of making each protocol state keep track of its own game objects (which would be a waste of resources), Netbound provides a way to 
keep track of these objects in one place, and pass them along to the protocol states that need them.

To define your own game objects, simply subclass `netbound.app.game.GameObject`, override the `update` method, and add them to the state's 
`_game_objects` set.

```python
# File: bullet.py

from netbound.app.game import GameObject

class Bullet(GameObject):
    def __init__(self, x: float, y: float, x_dir: int, y_dir: int, shooter_pid: bytes) -> None:
        super().__init__()
        self.x: float = x
        self.y: float = y
        self.x_dir: int = x_dir
        self.y_dir: int = y_dir
        self.speed: float = 450.0
        self.shooter_pid: bytes = shooter_pid

    def update(self, delta: float) -> None:
        self.x += self.x_dir * self.speed * delta
        self.y += self.y_dir * self.speed * delta
```

Then, in your state, you could add a bullet like so:

```python
# File: play_state.py
...
async def handle_shootbullet(self, p: pck.ShootBulletPacket) -> None:
    if p.from_pid == self._pid:
        await self._send_to_other(pck.ShootBulletPacket(from_pid=self._pid, to_pid=p.to_pid, exclude_sender=True, dx=p.dx, dy=p.dy))
        bullet: obj.Fireball = obj.Fireball(self._x, self._y, p.dx, p.dy, self._pid)
        self._game_objects.add(bullet)  # This is the line you need to add
    else:
        await self._po_(pck.ShootBulletPacket(from_pid=p.from_pid, dx=p.dx, dy=p.dy))
```

In other words, if a `ShootBullet` packet is received from the client, the server will add a new `Bullet` object to the state's `_game_objects` set, 
which is shared across all protocol states.

To actually tell the server to process these game objects, you need to call the server's `process_game_objects` method. Here, you pass in the game's 
framerate, which is often much higher than the server's tick rate. For this reason, it is very important to keep the `update` method of your game objects 
as lightweight as possible.

```python
# File: __main__.py
...
async with asyncio.TaskGroup() as tg:
    tg.create_task(server_app.start(initial_state=EntryState))
    tg.create_task(server_app.run(ticks_per_second=10))
    tg.create_task(server_app.process_game_objects(60))  # This is the line you need to add
```

When you want to delete a game object, simply pass it into the `_game_objects.discard` method. If you 
want to ensure only one object of a certain type exists, you can decorate the class with the `@unique` 
decorate (found in `netbound.app.game`). This will have the effect that any new additions of that type to 
`_game_objects` will replace the old one.

```python
# File: hat.py
from netbound.app.game import GameObject, unique

@unique
class Hat(GameObject):
    def __init__(self, x: float, y: float) -> None:
        super().__init__()
        self.x: float = x
        self.y: float = y
```

If you want to obtain the unique instance of a game object (if it exists), you can use the `get_unique` method
of `_game_objects`.

```python
# File: example.py
...
    hat1: obj.Hat = obj.Hat(0, 0)
    self._game_objects.add(hat)
    hat2: obj.Hat = obj.Hat(1, 1)
    self._game_objects.add(hat)  # This will replace the old hat
...
```

In terms of querying game objects from a protocol state, you can use the `netbound.schedule` function 
to recursively search for the object you want. For example, if you wanted to find if you have been hit 
by a bullet, you could do something like this:

```python
# File: play_state.py
...

async def _on_transition(self, previous_state_view: BaseState.View | None = None) -> None:
    await self._check_bullet_collisions()

async def _check_bullet_collisions(self) -> None:
    schedule(1/60, self._check_bullet_collisions)  # Recursively make sure this function is called every frame
    for bullet in self._game_objects.copy():  # Make a copy of the set to avoid modifying it while iterating
        if not isinstance(bullet, obj.Bullet):
            continue

        if self._is_colliding_with_bullet(bullet):  # This is a custom method you would need to implement
            await self._send_to_other(pck.HitByBulletPacket(from_pid=self._pid, to_pid=EVERYONE))  # For example
            bullet.queue_free()  # This will remove the bullet from the game objects set on the next frame
```

# Custom serializers and deserializers for packets
Netbound by default uses MessagePack for serialization and deserialization of packets. If you want to use a different format, you can 
create a subclass of the `netbound.packet.serializer.BaseSerializer` class and pass it to the server app via 
```python
server_app: ServerApp = ServerApp("localhost", 443)
server_app.set_serializer(MyCustomSerializer())
```
