import logging
import asyncio
import traceback
from datetime import datetime
import websockets as ws
import ssl
from uuid import uuid4
from server.packet import BasePacket, DisconnectPacket
from server.app.protocol import GameProtocol
from server.constants import EVERYONE
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from server.app.logging_adapter import ServerLoggingAdapter

class ServerApp:
    def __init__(self, host: str, port: int, ticks_per_second: int) -> None:
        self._host: str = host
        self._port: int = port
        self._tick_rate: float = 1 / ticks_per_second
        self._connected_protocols: dict[bytes, GameProtocol] = {}
        self._global_protos_packet_queue: asyncio.Queue[BasePacket] = asyncio.Queue()
    
        self._async_engine: AsyncEngine = create_async_engine("sqlite+aiosqlite:///server/database/netbound.db")
        self._async_session: async_sessionmaker = async_sessionmaker(bind=self._async_engine, class_=AsyncSession, expire_on_commit=False)

        self._logger: ServerLoggingAdapter = ServerLoggingAdapter(logging.getLogger(__name__))

    async def start(self) -> None:
        ssl_context: ssl.SSLContext = self._get_ssl_context("server/app/ssl/localhost.crt", "server/app/ssl/localhost.key")
        self._logger.info(f"Starting server on {self._host}:{self._port}")
        async with ws.serve(self.handle_connection, self._host, self._port, ssl=ssl_context):
            await asyncio.Future()

    async def run(self) -> None:
        self._logger.info("Running server tick loop")
        while True:
            start_time: float = datetime.now().timestamp()
            try:
                await self.tick()
            except Exception as e:
                self._logger.error(f"Unexpected error: {e}")
                traceback.print_exc()
            elapsed: float = datetime.now().timestamp() - start_time
            diff: float = self._tick_rate - elapsed
            if diff > 0:
                await asyncio.sleep(diff)
            elif diff < 0:
                self._logger.warning("Tick time budget exceeded by %s seconds", -diff)

    def _get_ssl_context(self, certpath: str, keypath: str) -> ssl.SSLContext:
        self._logger.info("Loading encryption key")
        ssl_context: ssl.SSLContext = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ssl_context.load_cert_chain(certpath, keypath)
        except FileNotFoundError:
            raise FileNotFoundError(f"No encryption key or certificate found. Please generate a pair and save them to {certpath} and {keypath}")

        return ssl_context



    async def handle_connection(self, websocket: ws.WebSocketServerProtocol) -> None:
        self._logger.info(f"New connection from {websocket.remote_address}")
        proto: GameProtocol = GameProtocol(websocket, uuid4().bytes, self._disconnect_protocol, self._async_session)
        self._connected_protocols[proto._pid] = proto
        await proto._start()


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


    async def tick(self) -> None:
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

    async def _disconnect_protocol(self, proto: GameProtocol, reason: str) -> None:
        self._logger.info(f"Disconnecting {proto}: {reason}")
        self._connected_protocols.pop(proto._pid)
        await self._global_protos_packet_queue.put(DisconnectPacket(reason=reason, from_pid=proto._pid, to_pid=EVERYONE))

    async def _send_to_client(self, proto: GameProtocol, p: BasePacket) -> None:
        try:
            await proto._websocket.send(p.serialize())
        except ws.ConnectionClosed as e:
            self._logger.error(f"Connection closed: {e}")
            await self._disconnect_protocol(proto, "Connection closed")