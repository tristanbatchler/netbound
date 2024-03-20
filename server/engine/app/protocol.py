from __future__ import annotations
import asyncio
import logging
import websockets as ws
import server.engine.packet as pck
import server.engine.state as st
from server.engine.state.base import BaseState
from sqlalchemy.ext.asyncio import async_sessionmaker
from typing import Callable, Coroutine, Any, Optional
from server.engine.constants import EVERYONE
from base64 import b64encode
from server.engine.app.logging_adapter import ProtocolLoggingAdapter

class GameProtocol:
    def __init__(
            self, 
            websocket: ws.WebSocketServerProtocol, 
            pid: bytes, 
            disconnect_callback: Callable[[GameProtocol, str], Coroutine[Any, Any, None]], 
            db_session_callback: async_sessionmaker
        ) -> None:
        """WARNING: This class must only be instantiated from within the server.app.ServerApp class"""
        self._websocket: ws.WebSocketServerProtocol = websocket
        self._pid: bytes = pid
        self._local_receive_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_protos_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._local_client_send_packet_queue: asyncio.Queue[pck.BasePacket] = asyncio.Queue()
        self._disconnect: Callable[[GameProtocol, str], Coroutine[Any, Any, None]] = disconnect_callback
        self._get_db_session: async_sessionmaker = db_session_callback
        self._state: Optional[st.BaseState] = None
        self._logger: ProtocolLoggingAdapter = ProtocolLoggingAdapter(logging.getLogger(__name__), {
            'pid': pid
        })

    def __repr__(self) -> str:
        return f"GameProtocol({b64encode(self._pid).decode()})"
    
    def __str__(self) -> str:
        return self.__repr__()

    async def _start(self, initial_state: st.BaseState) -> None:
        await self._change_state(initial_state(self._pid, self._change_state, self._local_protos_send_packet_queue.put, self._local_client_send_packet_queue.put, self._get_db_session))
        try:
            await self._listen_websocket()
        except ws.ConnectionClosedError:
            self._logger.debug(f"Connection closed")
            await self._disconnect(self, "Client disconnected")

    async def _listen_websocket(self) -> None:
        self._logger.debug(f"Starting protocol")

        async for message in self._websocket:
            if not isinstance(message, bytes):
                self._logger.error(f"Received non-bytes message: {message}")
                continue
            
            try:
                p: pck.BasePacket = pck.deserialize(message)
            except pck.MalformedPacketError as e:
                self._logger.error(f"Malformed packet: {e}")
                continue
            except pck.UnknownPacketError as e:
                self._logger.error(f"Unknown packet: {e}")
                continue
            except Exception as e:
                self._logger.error(f"Unexpected error: {e}")
                continue

            self._logger.debug(f"Received packet: {p}")
            
            # Store the packet in our local receive queue for processing next tick
            await self._local_receive_packet_queue.put(p)

        self._logger.debug(f"{self} stopped")
        await self._disconnect(self, "Client disconnected")

    async def _change_state(self, new_state: st.BaseState, previous_state_view: Optional[BaseState.View]=None) -> None:
        self._state = new_state
        await self._state.on_transition(previous_state_view)

    async def _process_packets(self) -> None:
        while not self._local_receive_packet_queue.empty():
            p: pck.BasePacket = await self._local_receive_packet_queue.get()
            if self._state:
                await self._state.handle_packet(p)
            self._logger.debug(f"Processed packet: {p}")