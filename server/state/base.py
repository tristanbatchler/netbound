from __future__ import annotations
from server.packet import BasePacket
from typing import Callable, Coroutine, Any

class BaseState:
    def __init__(self, pid: bytes, 
                 change_state_ref: Callable[[BaseState], None], 
                 queue_local_protos_send_ref: Callable[..., Coroutine[Any, Any, None]],
                 queue_local_client_send_ref: Callable[..., Coroutine[Any, Any, None]]) -> None:
        self._pid: bytes = pid
        self._change_states: Callable[[BaseState], None] = change_state_ref
        self._queue_local_protos_send: Callable[..., Coroutine[Any, Any, None]] = queue_local_protos_send_ref
        self._queue_local_client_send: Callable[..., Coroutine[Any, Any, None]] = queue_local_client_send_ref

    async def handle_packet(self, p: BasePacket) -> None:
        raise NotImplementedError("Subclasses must implement this method")
