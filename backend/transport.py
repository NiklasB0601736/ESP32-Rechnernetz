import asyncio
import json
import logging

import serial
from serial.tools import list_ports

LOG = logging.getLogger(__name__)


def ports():
    return [{"port": p.device, "description": p.description} for p in list_ports.comports()]


class SerialTransport:
    """One reader and serialized writes; bounded lines, no auto reset or auto port selection."""

    def __init__(self, port, receive, disconnected):
        self.port, self.receive, self.disconnected = port, receive, disconnected
        self.serial = None
        self.task = None
        self.lock = asyncio.Lock()
        self.stopping = False

    async def start(self):
        def open_port():
            connection = serial.Serial()
            connection.port = self.port
            connection.baudrate = 115200
            connection.timeout = 0.2
            connection.write_timeout = 1
            connection.dtr = False
            connection.rts = False
            connection.open()
            return connection
        self.serial = await asyncio.to_thread(open_port)
        self.task = asyncio.create_task(self.read())

    async def read(self):
        buffer = bytearray()
        dropping = False
        try:
            while not self.stopping:
                chunk = await asyncio.to_thread(self.serial.read, 512)
                for byte in chunk:
                    if byte == 10:
                        if not dropping:
                            try:
                                event = json.loads(buffer)
                                if isinstance(event, dict) and event.get("v") == 1:
                                    await self.receive(event)
                            except (ValueError, KeyError, TypeError):
                                LOG.debug("Ignored invalid serial line")
                        buffer.clear()
                        dropping = False
                    elif not dropping:
                        buffer.append(byte)
                        if len(buffer) > 4096:
                            buffer.clear()
                            dropping = True
        except (serial.SerialException, OSError) as exc:
            if not self.stopping:
                await self.disconnected(str(exc))

    async def send(self, message):
        async with self.lock:
            data = (json.dumps(message, separators=(",", ":")) + "\n").encode("ascii")
            if len(data) > 512:
                raise ValueError("Befehl zu lang")
            await asyncio.to_thread(self.serial.write, data)

    async def close(self):
        self.stopping = True
        if self.task:
            await self.task
        if self.serial:
            await asyncio.to_thread(self.serial.close)
