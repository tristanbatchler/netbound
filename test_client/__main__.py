import asyncio
from asyncio import Task
from typing import Literal, Optional, Any
import websockets as ws
import msgpack

class Client:
    EVERYONE: bytes = (0).to_bytes(16, "big")

    def __init__(self) -> None:
        self.my_pid: Optional[bytes] = None
        self.websocket: ws.WebSocketClientProtocol
        self.my_state: str = self.get_initial_state()

        self.username: str = input("Enter your username: ")
        self.password: str = input("Enter your password: ")

        self.known_others: dict[bytes, dict[str, Any]] = {}

    def get_initial_state(self) -> str:
        action: str = input("Enter 'l' to login or 'r' to register: ")
        if action not in ("l", "r"):
            raise ValueError("Invalid action")
        return "Login" if action == "l" else "Register"
        

    async def connect_websocket(self) -> None:
        self.websocket = await ws.connect("ws://localhost:8081")
        print("Connected")

    async def listen_websocket(self) -> None:
        try:
            async for message in self.websocket:
                assert isinstance(message, bytes)
                await self.handle_message(message)
        except ws.exceptions.ConnectionClosedError:
            print("Connection closed")
            await self.close_websocket()

    async def handle_message(self, message: bytes) -> None:
        packet = msgpack.unpackb(message, raw=False)
        p_type = list(packet.keys())[0]
        p_data = packet[p_type]

        if p_type == "Hello":
            await self.handle_hello(p_data)
        elif p_type == "Pid":
            await self.handle_pid(p_data)
        elif p_type == "Deny":
            await self.handle_deny(p_data)
        elif p_type == "Ok":
            await self.handle_ok(p_data)
        elif p_type == "Chat":
            await self.handle_chat(p_data)
        elif p_type == "Disconnect":
            await self.handle_disconnect(p_data)

    async def handle_hello(self, data: dict[str, Any]) -> None:
        if self.my_state == "Logged":
            pid: bytes = data["from_pid"]
            self.known_others[pid] = data["state_view"]
            print(f"{self.known_others[pid]['name']} connected")

    async def handle_pid(self, data: dict[str, Any]) -> None:
        self.my_pid = data["from_pid"]
        assert isinstance(self.my_pid, bytes)
        print(f"Received Pid packet: {self.my_pid.hex()[:8]}")

        await self.websocket.send(msgpack.packb({
            self.my_state: {
                "from_pid": self.my_pid,
                "username": self.username,
                "password": self.password
            }
        }, use_bin_type=True))

    async def handle_deny(self, data: dict[str, Any]) -> None:
        if self.my_state == "Login":
            print(f"Login denied: {data['reason']}")
        elif self.my_state == "Register":
            print(f"Register denied: {data['reason']}")
        else:
            print(f"Denied: {data['reason']}")

    async def handle_ok(self, data: dict[str, Any]) -> None:
        if self.my_state == "Login":
            print("Logged in")
            self.my_state = "Logged"
        elif self.my_state == "Register":
            print("Registered")

    async def handle_chat(self, data: dict[str, Any]) -> None:
        if self.my_state == "Logged":
            other_pid: bytes = data["from_pid"]
            if other := self.known_others.get(other_pid):
                other_name: str = other["name"]
            else:
                other_name = f"{other_pid.hex()[:8]}"

            print(f"{other_name}: {data['message']}")

    async def handle_disconnect(self, data: dict[str, Any]) -> None:
        if self.my_state == "Logged":
            print(f"{data['from_pid'].hex()[:8]} disconnected: {data['reason']}")

    async def poll_chat_input(self) -> None:
        while True:
            try:
                message = await asyncio.get_event_loop().run_in_executor(None, input, "")
                await self.websocket.send(msgpack.packb({
                    "Chat": {
                        "from_pid": self.my_pid,
                        "to_pid": self.EVERYONE,
                        "message": message
                    }
                }, use_bin_type=True))
            except asyncio.CancelledError:
                print("Stopped polling for chat input")
                await self.close_websocket()
                break

    async def close_websocket(self) -> None:
        if self.websocket:
            await self.websocket.close()
            print("WebSocket connection closed")

async def main() -> None:
    client = Client()
    await client.connect_websocket()
    async with asyncio.TaskGroup() as tg:
        tg.create_task(client.listen_websocket())
        tg.create_task(client.poll_chat_input())

    await client.close_websocket()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")
