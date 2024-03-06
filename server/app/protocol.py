from __future__ import annotations
import asyncio
import logging
import websockets as ws
import server.packet as pck
import server.state as st
from typing import Callable, Coroutine, Any, Optional
from server.constants import EVERYONE

class GameProtocol:
    def __init__(self, websocket: ws.WebSocketServerProtocol, pid: bytes, 
                 disconnect_ref: Callable[[GameProtocol, str], Coroutine[Any, Any, None]]) -> None:
        """WARNING: This class must only be instantiated from within the server.app.ServerApp class"""
        logging.debug(f"Assigned id {pid.hex()[:8]} to new connection")
        self._websocket: ws.WebSocketServerProtocol = websocket
        self._pid: bytes = pid
        self._local_receive_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_protos_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_client_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._disconnect: Callable = disconnect_ref
        self._state: Optional[st.BaseState] = None

    def __repr__(self) -> str:
        return f"GameProtocol({self._pid.hex()[:8]})"
    
    def __str__(self) -> str:
        return self.__repr__()

    async def _start(self) -> None:
        await self._change_state(st.EntryState(self._pid, self._change_state, self._local_protos_send_packet_queue.put, self._local_client_send_packet_queue.put))
        await self._listen_websocket()

    async def _listen_websocket(self) -> None:
        logging.debug(f"Starting protocol for id {self._pid.hex()[:8]}")

        async for message in self._websocket:
            if not isinstance(message, bytes):
                logging.error(f"Received non-bytes message: {message}")
                continue
            
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
            
            # Store the packet in our local receive queue for processing next tick
            await self._local_receive_packet_queue.put(p)

        logging.debug(f"{self} stopped")
        await self._disconnect(self, "Client disconnected")

    async def _change_state(self, new_state: st.BaseState) -> None:
        self._state = new_state
        await self._state.on_transition()

    async def _process_packets(self) -> None:
        while not self._local_receive_packet_queue.empty():
            p: pck.BasePacket = await self._local_receive_packet_queue.get()
            if self._state:
                await self._state.handle_packet(p)
            logging.debug(f"Processed packet: {p}")