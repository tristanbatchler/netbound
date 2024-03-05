from __future__ import annotations
from server.packet import BasePacket
from typing import Callable, Optional, Coroutine, Any
import logging

class BaseState:
    def __init__(self, pid: bytes, 
                 change_state_ref: Callable[[BaseState], None], 
                 queue_local_protos_send_ref: Callable[[BasePacket], Coroutine[Any, Any, None]],
                 queue_local_client_send_ref: Callable[[BasePacket], Coroutine[Any, Any, None]]) -> None:
        self._pid: bytes = pid
        self._change_states: Callable[[BaseState], None] = change_state_ref
        self._queue_local_protos_send: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_protos_send_ref
        self._queue_local_client_send: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_client_send_ref

    async def handle_packet(self, p: BasePacket) -> None:
        packet_name: str = p.__class__.__name__
        handler_name: str = f"handle_{packet_name.removesuffix("Packet").lower()}"
        handler: Optional[Callable[[BasePacket], Coroutine[Any, Any, None]]] = getattr(self, handler_name, None)
        if handler:
                await handler(p)
        else:
            logging.warning(f"State {self.__class__.__name__} does not have a handler for {packet_name} packets")            
