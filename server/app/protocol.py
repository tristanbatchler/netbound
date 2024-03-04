import asyncio
import logging
import websockets as ws
import server.packet as pck
import server.state as st
from server.constants import EVERYONE, ONLY_CLIENT, ONLY_PROTO
from typing import Callable, Coroutine, Any

class GameProtocol:
    def __init__(self, websocket: ws.WebSocketServerProtocol, pid: int, 
                 global_send_queue_put_ref: Callable[..., Coroutine[Any, Any, None]], 
                 disconnect_ref: Callable) -> None:
        """WARNING: This class must only be instantiated from within the server.app.ServerApp class"""
        logging.debug(f"Assigned id {pid} to new connection")
        self._websocket: ws.WebSocketServerProtocol = websocket
        self._pid: int = pid
        self._state: st.BaseState = st.EntryState(self._pid)
        self._local_receive_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._queue_global_send: Callable[..., Coroutine[Any, Any, None]] = global_send_queue_put_ref
        self._disconnect: Callable = disconnect_ref

    async def _start(self) -> None:
        await self._queue_global_send(pck.PIDPacket(pid=self._pid, from_pid=self._pid, to_pid=ONLY_CLIENT))
        await self._listen_websocket()

    async def _listen_websocket(self) -> None:
        logging.debug(f"Starting protocol for id {self._pid}")

        async for message in self._websocket:
            try:
                p: pck.BasePacket = pck.deserialize(message)
            except pck.MalformedPacketError as e:
                logging.error(f"Malformed packet: {e}")
                continue
            except pck.UnknownPacketError as e:
                logging.error(f"Unknown packet: {e}")
                continue
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                continue

            logging.debug(f"Received packet: {p}")

            
            await self._queue_global_send(p)

        logging.debug(f"Protocol for id {self._pid} stopped")
        await self._disconnect(self, "Client disconnected")

    async def _process_packets(self) -> None:
        while not self._local_receive_packet_queue.empty():
            p: pck.BasePacket = self._local_receive_packet_queue.get_nowait()
            self._state.handle_packet(p)
            logging.debug(f"Processed packet: {p}")