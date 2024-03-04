import logging
import asyncio
import traceback
from datetime import datetime
import websockets as ws
from uuid import uuid4
from server.packet import BasePacket, DisconnectPacket, PIDPacket
from server.app.protocol import GameProtocol
from server.constants import EVERYONE, ONLY_CLIENT, ONLY_PROTO

class ServerApp:
    def __init__(self, host: str, port: int, ticks_per_second: int) -> None:
        self._host: str = host
        self._port: int = port
        self._tick_rate: float = 1 / ticks_per_second
        self._connected_protocols: dict[bytes, GameProtocol] = {}
        self._global_packet_queue: asyncio.Queue[BasePacket] = asyncio.Queue()

    async def start(self) -> None:
        logging.info(f"Starting server on {self._host}:{self._port}")
        async with ws.serve(self.handle_connection, self._host, self._port):
            await asyncio.Future()

    async def run(self) -> None:
        logging.info("Running server tick loop")
        while True:
            start_time: float = datetime.now().timestamp()
            try:
                await self.tick()
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                traceback.print_exc()
            elapsed: float = datetime.now().timestamp() - start_time
            diff: float = self._tick_rate - elapsed
            if diff > 0:
                await asyncio.sleep(diff)
            elif diff < 0:
                logging.warning("Tick time budget exceeded by %s seconds", -diff)


    async def handle_connection(self, websocket: ws.WebSocketServerProtocol) -> None:
        logging.info(f"New connection from {websocket.remote_address}")
        proto: GameProtocol = GameProtocol(websocket, uuid4().bytes, self._global_packet_queue.put, self._disconnect_protocol)
        self._connected_protocols[proto._pid] = proto
        await proto._start()


    async def _dispatch_packets(self) -> None:
        while not self._global_packet_queue.empty():
            p: BasePacket = self._global_packet_queue.get_nowait()
            
            to_pids: list[bytes] = p.to_pid if isinstance(p.to_pid, list) else [p.to_pid]

            for to_pid in to_pids:
                if to_pid == p.from_pid:
                    logging.error(f"Packet {p} was dropped because its direction is ambiguous")
                    continue

                elif to_pid in (EVERYONE, ONLY_CLIENT, ONLY_PROTO) and p.from_pid in (EVERYONE, ONLY_CLIENT, ONLY_PROTO):
                    logging.error(f"Packet {p} was dropped because its source and destination are incompatible")
                    continue

                elif to_pid == EVERYONE:
                    for _, proto in self._connected_protocols.items():
                        await self._send_to_client(proto, p)
                        
                elif to_pid == ONLY_PROTO:
                    # Assume the packet's destination PID is that of its source
                    if to_proto := self._connected_protocols.get(p.from_pid):
                        await to_proto._local_receive_packet_queue.put(p)
                    else:
                        logging.error(f"Packet {p} was sent to a disconnected protocol")
                        logging.error("Poop1")
                        continue

                elif to_pid == ONLY_CLIENT:
                    if from_proto := self._connected_protocols.get(p.from_pid):
                        await self._send_to_client(from_proto, p)
                    else:
                        logging.error(f"Packet {p} was sent from a disconnected protocol")
                        logging.error("Poop2")
                        continue 
                
                # If we get to here, destination should be a specific PID
                elif specific_to_proto  := self._connected_protocols.get(to_pid):
                    await specific_to_proto._local_receive_packet_queue.put(p)
                else:
                    logging.error(f"Packet {p} was sent to a disconnected protocol")
                    logging.error("Poop3")


    async def tick(self) -> None:
        await self._dispatch_packets()
        for _, proto in self._connected_protocols.items():
            await proto._process_packets()

    async def _disconnect_protocol(self, proto: GameProtocol, reason: str) -> None:
        logging.info(f"Disconnecting protocol {proto._pid.hex()}: {reason}")
        self._connected_protocols.pop(proto._pid)
        await self._global_packet_queue.put(DisconnectPacket(reason=reason, from_pid=proto._pid, to_pid=EVERYONE))

    async def _send_to_client(self, proto: GameProtocol, p: BasePacket) -> None:
        try:
            await proto._websocket.send(p.serialize())
        except ws.ConnectionClosed as e:
            logging.error(f"Connection closed: {e}")
            await self._disconnect_protocol(proto, "Connection closed")