import asyncio
import websockets as ws
import json

class Client:
    def __init__(self):
        self.my_pid = None

    async def listen_websocket(self):
        async with ws.connect("ws://localhost:8081") as websocket:
            print("Connected")
            async for message in websocket:
                print(f"Received message: {message}")

                packet = json.loads(message)
                p_type = list(packet.keys())[0]
                p_data = packet[p_type]
                
                if p_type == "pid":
                    self.my_pid = p_data["pid"]
                    print(f"Assigned id {self.my_pid}")

                    await websocket.send(json.dumps({
                        "login": {
                            "username": "test",
                            "password": "123",
                            "from_pid": self.my_pid,
                            "to_pid": -3
                        }
                    }))

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

