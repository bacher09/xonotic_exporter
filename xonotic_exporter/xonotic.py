import asyncio
import time
from xrcon import utils
from .metrics_parser import IllegalState, XonoticMetricsParser
import enum


PING_Q2_PACKET = b"\xFF\xFF\xFF\xFFping"
PONG_Q2_PACKET = b"\xFF\xFF\xFF\xFFack"
# TODO: add logging


class RetryError(Exception):
    pass


class RconMode(enum.IntEnum):
    NONSECURE = 0
    SECURE_TIME = 1
    SECURE_CHALLENGE = 2


class XonoticProtocol:

    def __init__(self, loop, rcon_password, rcon_mode):
        self.loop = loop
        self.transport = None
        self.addr = None
        self.ping_future = None
        self.ping_lock = asyncio.Lock(loop=loop)
        self.challenge_future = None
        self.challenge_lock = asyncio.Lock(loop=loop)
        self.rcon_queue = asyncio.Queue(maxsize=50, loop=loop)
        self.rcon_password = rcon_password
        self.set_mode(rcon_mode)

    def set_mode(self, rcon_mode):
        if isinstance(rcon_mode, int):
            rcon_mode = RconMode(rcon_mode)

        if not isinstance(rcon_mode, RconMode):
            raise ValueError("Bad rcon_mode")

        self.rcon_mode = rcon_mode

    def connection_made(self, transport):
        self.transport = transport
        self.addr = self.transport.get_extra_info('peername')

    def datagram_received(self, data, addr):
        if addr != self.addr:
            # ignore datagrams from wrong address
            return

        if data == PONG_Q2_PACKET and self.ping_future is not None:
            if self.ping_future.done() or self.ping_future.cancelled():
                return

            self.ping_future.set_result(time.monotonic())
        elif data.startswith(utils.CHALLENGE_RESPONSE_HEADER):
            if self.challenge_future is None:
                return

            challenge_future = self.challenge_future
            if challenge_future.done() or challenge_future.cancelled():
                return

            challenge_future.set_result(utils.parse_challenge_response(data))
        elif data.startswith(utils.RCON_RESPONSE_HEADER):
            rcon_output = utils.parse_rcon_response(data)
            self.rcon_queue.put_nowait(rcon_output)

    def error_received(self, exc):
        pass

    def connection_lost(self, exc):
        pass

    async def ping(self):
        "Return rtt time for remote server"
        await self.ping_lock
        try:
            self.ping_future = asyncio.Future(loop=self.loop)
            start_time = time.monotonic()
            self.transport.sendto(PING_Q2_PACKET)
            end_time = await self.ping_future
            return end_time - start_time
        finally:
            self.ping_future = None
            self.ping_lock.release()

    async def getchallenge(self):
        "Returns challenge from server"
        await self.challenge_lock
        try:
            self.challenge_future = asyncio.Future(loop=self.loop)
            self.transport.sendto(utils.CHALLENGE_PACKET)
            challenge = await self.challenge_future
            return challenge
        finally:
            self.challenge_future = None
            self.challenge_lock.release()

    def rcon_nonsecure(self, command, password):
        packet = utils.rcon_nosecure_packet(password, command)
        self.transport.sendto(packet)

    def rcon_secure_time(self, command, password):
        # TODO: add time diff
        packet = utils.rcon_secure_time_packet(password, command)
        self.transport.sendto(packet)

    def rcon_secure_challenge(self, command, password, challenge):
        packet = utils.rcon_secure_challenge_packet(password, challenge,
                                                    command)

        self.transport.sendto(packet)

    async def rcon(self, command):
        if self.rcon_mode == RconMode.NONSECURE:
            self.rcon_nonsecure(command, password=self.rcon_password)
        elif self.rcon_mode == RconMode.SECURE_TIME:
            self.rcon_secure_time(command, password=self.rcon_password)
        elif self.rcon_mode == RconMode.SECURE_CHALLENGE:
            challenge = await self.getchallenge()
            self.rcon_secure_challenge(command, password=self.rcon_password,
                                       challenge=challenge)


class XonoticMetricsProtocol(XonoticProtocol):

    def __init__(self, loop, rcon_password, rcon_mode, retries_count=3,
                 timeout=3):
        super().__init__(loop, rcon_password, rcon_mode)
        self.retries_count = retries_count
        self.timeout = timeout

    async def ping(self):
        rtt = await self.retry(super().ping)
        return rtt

    async def get_metrics(self):
        ping_task = asyncio.ensure_future(self.ping(), loop=self.loop)
        rcon_metrics = asyncio.ensure_future(self.get_rcon_metrics(),
                                             loop=self.loop)

        await asyncio.wait([ping_task, rcon_metrics], loop=self.loop)
        metrics = rcon_metrics.result()
        rtt = ping_task.result()
        metrics['ping'] = rtt
        return metrics

    async def get_rcon_metrics(self):
        async def try_load_metrics():
            await self.retry(self.rcon, "sv_public\0status 1")
            metrics = await self.read_rcon_metrics()
            return metrics

        value = await self.retry(try_load_metrics)
        return value

    async def retry(self, async_fun, *args, **kwargs):
        for i in range(self.retries_count):
            try:
                task = async_fun(*args, **kwargs)
                value = await asyncio.wait_for(task, self.timeout,
                                               loop=self.loop)
            except (OSError, asyncio.TimeoutError, IllegalState):
                continue
            else:
                return value

        raise RetryError("Retries limit exceeded")

    async def read_rcon_metrics(self):
        parser = XonoticMetricsParser()
        start_time = time.monotonic()
        val = await asyncio.wait_for(self.rcon_queue.get(), self.timeout,
                                     loop=self.loop)
        parser.feed_data(val)
        rtt_time = time.monotonic() - start_time
        while not parser.done:
            wait_time = max(rtt_time * 1.6, 0.2)
            start_time = time.monotonic()
            val = await asyncio.wait_for(self.rcon_queue.get(), wait_time,
                                         loop=self.loop)
            read_time = time.monotonic() - start_time
            rtt_time = rtt_time * 0.85 + read_time * 0.15
            parser.feed_data(val)

        return parser.metrics
