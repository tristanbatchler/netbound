import logging
import asyncio
import traceback
from datetime import datetime
from typing import Optional, Type
import websockets as ws
from ssl import SSLContext
from uuid import uuid4
from netbound.packet import BasePacket, DisconnectPacket, register_packet
from netbound.app.protocol import _GameProtocol
from netbound.constants import EVERYONE
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine
from netbound.app.logging_adapter import ServerLoggingAdapter
from netbound.state import BaseState
from types import ModuleType

class ServerApp:
    """
    The main server application. Instantiate this class to initialize the server to listen for incoming connections on 
    the specified host, port, and database engine. Optionally, you can provide an SSLContext object to enable secure connections.

    To make the server start listening for incoming client connections, call the `start` method with the initial state 
    class as the argument (this will be a subclass of `netbound.state.BaseState`).

    To inject custom packets into the server, call the `register_packets` method with the module containing the custom 
    packets as the argument. Without this step, the server will not be able to recognize custom packets.

    To run the server's main tickloop, call the `run` method with the desired ticks per second as the argument. This will 
    allow the server to start accepting incoming client packets and dispatching packets from the global queue at the desired 
    rate. This in turn will allow each connected client's internal state to be updated.
    """
    def __init__(self, host: str, port: int, db_engine: AsyncEngine, ssl_context: Optional[SSLContext]=None) -> None:
        """
        Initializes the server with the specified host, port, database engine and optional SSL context. 

        To create the database engine, use the `sqlalchemy.ext.asyncio.create_async_engine` function. For example:

        ```
        from sqlalchemy.ext.asyncio import create_async_engine
        db_engine = create_async_engine("sqlite+aiosqlite:///database.sqlite3")
        server = ServerApp("localhost", 8000, db_engine)
        ```

        To create an SSL context, use the ssl.SSLContext class. For example:
        
        ```
        from ssl import SSLContext, PROTOCOL_TLS_SERVER
        ssl_context = SSLContext(PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile, keyfile)
        ...
        ```
        """
        self.host: str = host
        self.port: int = port
        self.ssl_context: Optional[SSLContext] = ssl_context

        self._connected_protocols: dict[bytes, _GameProtocol] = {}
        self._global_protos_packet_queue: asyncio.Queue[BasePacket] = asyncio.Queue()
    
        self._async_engine: AsyncEngine = db_engine
        self._async_session: async_sessionmaker = async_sessionmaker(bind=self._async_engine, class_=AsyncSession, expire_on_commit=False)

        self._logger: ServerLoggingAdapter = ServerLoggingAdapter(logging.getLogger(__name__))

        self.initial_state: BaseState | None = None  # This will be set by the the start method

    async def start(self, initial_state: Type[BaseState]) -> None:
        """
        Starts listening for incoming connections. The initial state is used to create the state object for each client 
        that connects. This, in turn, will be used to manage the client's internal state for sending and receiving packets. 
        The initial state must be a subclass of `netbound.state.BaseState`.
        """
        self.initial_state = initial_state
        self._logger.info(f"Starting server on {self.host}:{self.port}")
        async with ws.serve(self._handle_connection, self.host, self.port, ssl=self.ssl_context):
            await asyncio.Future()

    def register_packets(self, packet_module: ModuleType) -> None:
        """
        Registers all packet classes in the specified module. This is required for the server to recognize custom packets.
        """
        for packet_name in dir(packet_module):
            if packet_name.endswith("Packet"):
                packet_class = getattr(packet_module, packet_name)
                if issubclass(packet_class, BasePacket):
                    register_packet(packet_class)

    async def run(self, ticks_per_second: int) -> None:
        """
        Runs the server's main tick loop. This will allow the server to start accepting incoming client packets and 
        dispatching packets from the global queue at the desired rate. This in turn will allow each connected client's 
        internal state to be updated.
        """
        tick_rate: float = 1 / ticks_per_second
        self._logger.info("Running server tick loop")
        while True:
            start_time: float = datetime.now().timestamp()
            try:
                await self._tick()
            except Exception as e:
                self._logger.error(f"Unexpected error: {e}")
                traceback.print_exc()
            elapsed: float = datetime.now().timestamp() - start_time
            diff: float = tick_rate - elapsed
            if diff > 0:
                await asyncio.sleep(diff)
            elif diff < 0:
                self._logger.warning("Tick time budget exceeded by %s seconds", -diff)

    async def _handle_connection(self, websocket: ws.WebSocketServerProtocol) -> None:
        self._logger.info(f"New connection from {websocket.remote_address}")
        proto: _GameProtocol = _GameProtocol(websocket, uuid4().bytes, self._disconnect_protocol, self._async_session)
        self._connected_protocols[proto._pid] = proto
        await proto._start(self.initial_state)


    async def _dispatch_packets(self) -> None:
        while not self._global_protos_packet_queue.empty():
            p: BasePacket = await self._global_protos_packet_queue.get()
            self._logger.debug(f"Dispatching {p.__class__.__name__} packet")
            
            to_pids: list[Optional[bytes]] = p.to_pid if isinstance(p.to_pid, list) else [p.to_pid]

            for to_pid in to_pids:
                if to_pid is None:
                    self._logger.error(f"Packet {p} in the global protos queue was dropped because its "
                                  "destination PID is None. If you are trying to send to the "
                                  "client, use the local client queue instead")
                    continue

                if to_pid == p.from_pid:
                    self._logger.error(f"Packet {p} was dropped because its direction is ambiguous in the proto-to-proto queue")
                    continue

                elif p.from_pid == EVERYONE:
                    self._logger.error(f"Packet {p} was dropped because its source PID must be specific")
                    continue

                elif p.exclude_sender and p.to_pid != EVERYONE:
                    self._logger.error(f"Packet {p} was dropped because exclude_sender is only compatible with the EVERYONE destination")
                    continue

                elif to_pid == EVERYONE:
                    for _, proto in self._connected_protocols.items():
                        if p.exclude_sender and proto._pid == p.from_pid:
                            continue
                        await proto._local_receive_packet_queue.put(p)
                        self._logger.debug(f"Added {p.__class__.__name__} packet to {proto}'s receive queue")
                
                # If we get to here, destination should be a specific PID
                elif specific_to_proto  := self._connected_protocols.get(to_pid):
                    await specific_to_proto._local_receive_packet_queue.put(p)
                else:
                    self._logger.error(f"Packet {p} was sent to a disconnected protocol")


    async def _tick(self) -> None:
        # Grab the top outbound packet from each protocol and put it in the global queue
        for _, proto in self._connected_protocols.copy().items():
            if not proto._local_protos_send_packet_queue.empty():
                p_to_other: BasePacket = await proto._local_protos_send_packet_queue.get()
                self._logger.debug(f"Popped {p_to_other.__class__.__name__} packet from {proto}'s proto-to-proto send queue")
                await self._global_protos_packet_queue.put(p_to_other)
            
            if not proto._local_client_send_packet_queue.empty():
                p_to_client: BasePacket = await proto._local_client_send_packet_queue.get()
                self._logger.debug(f"Popped {p_to_client.__class__.__name__} packet from {proto}'s client send queue")
                await self._send_to_client(proto, p_to_client)

        # Dispatch all packets in the global proto-to-proto queue to their respective protocols' inbound queues
        await self._dispatch_packets()
        
        # Process all inbound packets for each protocol
        for _, proto in self._connected_protocols.copy().items():
            await proto._process_packets()

    async def _disconnect_protocol(self, proto: _GameProtocol, reason: str) -> None:
        self._logger.info(f"Disconnecting {proto}: {reason}")
        self._connected_protocols.pop(proto._pid)
        await self._global_protos_packet_queue.put(DisconnectPacket(from_pid=proto._pid, to_pid=EVERYONE, reason=reason))

    async def _send_to_client(self, proto: _GameProtocol, p: BasePacket) -> None:
        try:
            await proto._websocket.send(p.serialize())
        except ws.ConnectionClosed as e:
            self._logger.error(f"Connection closed: {e}")
            await self._disconnect_protocol(proto, "Connection closed")