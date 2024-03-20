from __future__ import annotations
from server.engine.packet import BasePacket
from typing import Callable, Optional, Coroutine, Any
from sqlalchemy.ext.asyncio import async_sessionmaker
from server.engine.app.logging_adapter import StateLoggingAdapter
from dataclasses import dataclass
import logging

class BaseState:
    @dataclass
    class View:
        pass

    def __init__(
            self, 
            pid: bytes, 
            change_state_callback: Callable[[BaseState, BaseState.View], Coroutine[Any, Any, None]], 
            queue_local_protos_send_callback: Callable[[BasePacket], Coroutine[Any, Any, None]],
            queue_local_client_send_callback: Callable[[BasePacket], Coroutine[Any, Any, None]], 
            get_db_session_callback: async_sessionmaker
        ) -> None:
        self._pid: bytes = pid
        self._change_states: Callable[[BaseState, BaseState.View], Coroutine[Any, Any, None]] = change_state_callback
        self._queue_local_protos_send: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_protos_send_callback
        self._queue_local_client_send: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_client_send_callback
        self._get_db_session: async_sessionmaker = get_db_session_callback
        self._logger: StateLoggingAdapter = StateLoggingAdapter(logging.getLogger(__name__), {
            'pid': pid,
            'state': self.__class__.__name__
        })

    
    @property
    def view(self) -> View:
        params: dict[str, Any] = {}
        for k in self.View.__dataclass_fields__:
            value: Any = getattr(self, k, None) or getattr(self, f"_{k}", None)
            if value is not None:
                params[k] = value
            else:
                self._logger.error(f"State {self.__class__.__name__} has no value for {k}")

        return self.View(**params)

    @property
    def view_dict(self) -> dict[str, Any]:
        return self.view.__dict__
    
    async def change_states(self, new_state: type[BaseState]) -> None:
        await self._change_states(new_state(self._pid, self._change_states, self._queue_local_protos_send, self._queue_local_client_send, self._get_db_session), self.view)

    async def on_transition(self, previous_state_view: Optional[BaseState.View]=None) -> None:
         pass

    async def handle_packet(self, p: BasePacket) -> None:
        packet_name: str = p.__class__.__name__.removesuffix("Packet").lower()
        handler_name: str = f"handle_{packet_name}"
        if handler := getattr(self, handler_name, None):
            await handler(p)
        else:
            self._logger.warning(f"State {self.__class__.__name__} does not have a handler for {packet_name} packets")            
