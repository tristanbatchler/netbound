from __future__ import annotations
from netbound.packet import BasePacket
from typing import Callable, Optional, Coroutine, Any
from sqlalchemy.ext.asyncio import async_sessionmaker
from netbound.app.logging_adapter import StateLoggingAdapter
from netbound.app.game import GameObject, GameObjectsSet
from dataclasses import dataclass
import logging
from abc import ABC

class BaseState(ABC):
    """
    The base state class. All user-defined states must inherit from this class. Definitions you are encouraged to override are:
    * `View` - a dataclass that represents the state's public view. This should contain variables that have the same name as this state's internal variables, but with no leading underscore
    * `_on_transition` - a method that automatically fires when the state is changed, and has access to the previous state's public view
    * `handle_packetnamehere` - a method that automatically fires when a packet of type `PacketNameHerePacket` is received (you will create as many or as few of these as you need for this state)
    """
    @dataclass
    class View:
        """
        A dataclass that represents the state's public view. This is used to expose some of the state's 
        internal variables to the outside world, and can be useful for transitioning between states or 
        serializing and sending the state over the network.
        """
        pass

    def __init__(
            self, 
            pid: bytes, 
            game_objects: GameObjectsSet,
            change_state_callback: Callable[[BaseState, BaseState.View], Coroutine[Any, Any, None]], 
            queue_local_protos_send_callback: Callable[[BasePacket], Coroutine[Any, Any, None]],
            queue_local_client_send_callback: Callable[[BasePacket], Coroutine[Any, Any, None]], 
            get_db_session_callback: async_sessionmaker
        ) -> None:
        """
        Instantiates the state with the specified PID, and various callback functions used for communicating with the server. 
        You are **strongly** discouraged from calling this method directly. Instead, let the server do this for you when you 
        provide the initial state class to the `ServerApp.start` method. This, together with the state's own `_change_states` 
        function, will take care of a lot of this for you.
        """
        self._pid: bytes = pid
        self._game_objects: GameObjectsSet = game_objects
        self._change_states: Callable[[BaseState, BaseState.View], Coroutine[Any, Any, None]] = change_state_callback
        self._send_to_other: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_protos_send_callback
        self._send_to_client: Callable[[BasePacket], Coroutine[Any, Any, None]] = queue_local_client_send_callback
        self._get_db_session: async_sessionmaker = get_db_session_callback
        self._logger: StateLoggingAdapter = StateLoggingAdapter(logging.getLogger(__name__), {
            'pid': pid,
            'state': self.__class__.__name__
        })

    
    @property
    def view(self) -> View:
        """
        Generates and returns the state's public view. This is used to expose some of the state's internal variables to the 
        outside world.
        """
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
        """
        Generates and returns the state's public view as a dictionary. This is useful for serializing the state and sending it 
        over the network.
        """
        return self.view.__dict__
    
    async def change_states(self, new_state: type[BaseState]) -> None:
        """
        Changes the state to the specified new state, passing along the necessary callbacks, the current PID, and the current 
        state's public view. When this is done, the new state's `_on_transition` method will immediately be called (if it is overridden).
        
        By passing the public view, the new state can access some of the "old" state's internal variables by way of the `_on_transition` 
        method's implemtnation.
        """
        await self._change_states(new_state(self._pid, self._game_objects, self._change_states, self._send_to_other, self._send_to_client, self._get_db_session), self.view)

    async def _on_transition(self, previous_state_view: Optional[BaseState.View]=None) -> None:
        """
        This method is called automatically when the state is changed. It has access to fields from the previous state's public view, 
        so you are free to do with them as you please. By default, this method does nothing. You should **NOT** call this method directly.
        """
        pass
    
    async def _handle_packet(self, p: BasePacket) -> None:
        packet_name: str = p.__class__.__name__.removesuffix("Packet").lower()
        handler_name: str = f"handle_{packet_name}"
        if handler := getattr(self, handler_name, None):
            await handler(p)
        else:
            self._logger.warning(f"State {self.__class__.__name__} does not have a handler for {packet_name} packets")            
