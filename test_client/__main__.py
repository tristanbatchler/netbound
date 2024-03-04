import asyncio
import websockets as ws
import msgpack

from typing import Literal
tb_params: tuple[int, Literal["big", "little"]] = (16, "big")

EVERYONE: bytes = (0).to_bytes(*tb_params)
ONLY_CLIENT: bytes = (1).to_bytes(*tb_params)
ONLY_PROTO: bytes = (2).to_bytes(*tb_params)

class Client:
    def __init__(self):
        self.my_pid = None

    async def listen_websocket(self):
        async with ws.connect("ws://localhost:8081") as websocket:
            print("Connected")
            async for message in websocket:
                print(f"Received message: {message}")

                packet = msgpack.unpackb(message, raw=False)
                p_type = list(packet.keys())[0]
                p_data = packet[p_type]

                print(f"Decoded packet: {p_type} {p_data}")
                
                if p_type == "Pid":
                    self.my_pid = p_data["pid"]
                    print(f"Assigned id {self.my_pid.hex()}")

                    await websocket.send(msgpack.packb({
                        "login": {
                            "username": "test",
                            "password": "123",
                            "from_pid": self.my_pid,
                            "to_pid": ONLY_PROTO
                        }
                    }, use_bin_type=True))

                elif p_type == "deny":
                    print(f"Denied: {p_data['reason']}")


async def main():
    client = Client()
    async with asyncio.TaskGroup() as tg:
        await tg.create_task(client.listen_websocket())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")

