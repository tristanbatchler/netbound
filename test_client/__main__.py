import asyncio
import websockets as ws
import msgpack
from typing import Literal

tb_params: tuple[int, Literal["big", "little"]] = (16, "big")

EVERYONE: bytes = (0).to_bytes(*tb_params)

class Client:
    def __init__(self):
        self.my_pid = None
        self.my_state = "Entry"
        self.websocket = None

    async def connect_websocket(self):
        self.websocket = await ws.connect("ws://localhost:8081")
        print("Connected")


    async def listen_websocket(self):
        try:
            async for message in self.websocket:
                packet = msgpack.unpackb(message, raw=False)
                p_type = list(packet.keys())[0]
                p_data = packet[p_type]

                if p_type == "Hello":
                    print(f"Hello from {p_data['from_pid'].hex()[:8]} with favourite number {p_data['favourite_number']}")

                if self.my_state == "Entry":
                    if p_type == "Pid":
                        self.my_pid = p_data["from_pid"]
                        print(f"Assigned id {self.my_pid.hex()[:8]}")

                        await self.websocket.send(msgpack.packb({
                            "Login": {
                                "username": self.my_pid.hex()[:8],
                                "password": "123",
                                "from_pid": self.my_pid,
                                "to_pid": self.my_pid
                            }
                        }, use_bin_type=True))

                    elif p_type == "Deny":
                        print(f"Denied: {p_data['reason']}")

                    elif p_type == "Ok":
                        print("Ok")
                        self.my_state = "Logged"

                elif self.my_state == "Logged":
                    if p_type == "Chat":
                        sender = p_data["from_pid"].hex()[:8]
                        print(f"{sender}: {p_data['message']}")

                    elif p_type == "Disconnect":
                        sender = p_data["from_pid"].hex()[:8]
                        reason = p_data["reason"]
                        if reason is None:
                            reason = "unforeseeable circumstances"
                        print(f"({sender} has disconnected due to {reason})")
        except ws.exceptions.ConnectionClosedError:
            print("Connection closed")
            await self.close()

    async def poll_chat_input(self):
        while True:
            try:
                message = await asyncio.get_event_loop().run_in_executor(None, input, "")
                await self.websocket.send(msgpack.packb({
                    "Chat": {
                        "from_pid": self.my_pid,
                        "to_pid": EVERYONE,
                        "message": message
                    }
                }, use_bin_type=True))
            except asyncio.CancelledError:
                await self.close_websocket()
                break

    async def close_websocket(self):
        if self.websocket:
            await self.websocket.close()
            print("WebSocket connection closed")

async def main():
    client = Client()
    await client.connect_websocket()
    async with asyncio.TaskGroup() as tg:
        tg.create_task(client.listen_websocket())
        tg.create_task(client.poll_chat_input())
    client.close_websocket()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")
