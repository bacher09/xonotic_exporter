import asyncio
import time
from xrcon import utils
import enum
import re


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

    async def ping(self, timeout=3.0):
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
        rtt = await self.retry(super().ping, timeout=self.timeout)
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


class IllegalState(ValueError):
    pass


class XonoticMetricsParser:

    COLORS_RE = re.compile(b"\^(?:\d|x[\dA-Fa-f]{3})")
    SV_PUBLIC_RE = re.compile(b'^"sv_public"\s+is\s+"(-?\d+)"')
    HOST_RE = re.compile(b'^host:\s+(.+)$')
    MAP_RE = re.compile(b'^map:\s+([^\s]+)')
    TIMING_RE = re.compile(
        b'^timing:\s+'
        b'(?P<cpu>-?[\d\.]+)%\s+CPU,\s+'
        b'(?P<lost>-?[\d\.]+)%\s+lost,\s+'
        b'offset\s+avg\s+(?P<offset_avg>-?[\d\.]+)ms,\s+'
        b'max\s+(?P<max>-?[\d\.]+)ms,\s+'
        b'sdev\s+(?P<sdev>-?[\d\.]+)ms'
    )
    PLAYERS_RE = re.compile(
        b'^players:\s+(?P<count>\d+)\s+active\s+\((?P<max>\d+)\s+max\)'
    )

    def __init__(self):
        self.state_fun = self.parse_sv_public
        self.done = False
        self.players_count = None
        self.status_players = None
        self.metrics = {}
        self.metrics['players_active'] = 0
        self.metrics['players_spectators'] = 0
        self.metrics['players_bots'] = 0
        self.old_data = b""

    def feed_data(self, binary_data):
        data = self.old_data + binary_data
        while not self.done:
            try:
                binary_line, data = data.split(b'\n', 1)
            except ValueError:
                # not enough data for unpacking
                self.old_data = data
                return
            else:
                self.process_line(binary_line)

    def process_line(self, line):
        if not self.done:
            self.state_fun(line)
        else:
            self.state_error(line)

    def state_error(self, line):
        # TODO: add more info about state
        raise IllegalState("Received bad input")

    def parse_sv_public(self, line):
        sv_public_m = self.SV_PUBLIC_RE.match(line)
        if sv_public_m is not None:
            val = sv_public_m.group(1)
            try:
                val = int(val)
            except ValueError:
                pass
            else:
                self.metrics['sv_public'] = val

            self.state_fun = self.parse_hostname  # update state
        else:
            self.state_error(line)

    def parse_hostname(self, line):
        host_m = self.HOST_RE.match(line)
        if host_m is not None:
            val = host_m.group(1).strip()
            self.metrics['hostname'] = val.decode("utf8", "ignore")
            self.state_fun = self.parse_version
        else:
            self.state_error(line)

    def parse_version(self, line):
        if line.startswith(b"version:"):
            self.state_fun = self.parse_protocol
        else:
            self.state_error(line)

    def parse_protocol(self, line):
        if line.startswith(b"protocol:"):
            self.state_fun = self.parse_map
        else:
            self.state_error(line)

    def parse_map(self, line):
        map_m = self.MAP_RE.match(line)
        if map_m is not None:
            val = map_m.group(1)
            self.metrics['map'] = val.decode("utf8", "ignore")
            self.state_fun = self.parse_timing
        else:
            self.state_error(line)

    def parse_timing(self, line):
        timing_m = self.TIMING_RE.match(line)
        if timing_m is not None:
            vals = timing_m.groupdict()
            for key, val in vals.items():
                try:
                    val = float(val)
                except ValueError:
                    pass
                else:
                    self.metrics["timing_{0}".format(key)] = val

            self.state_fun = self.parse_players
        else:
            self.state_error(line)

    def parse_players(self, line):
        players_m = self.PLAYERS_RE.match(line)
        if players_m is not None:
            for key, val in players_m.groupdict().items():
                try:
                    val = int(val)
                except ValueError:
                    pass
                else:
                    self.metrics["players_{0}".format(key)] = val

            self.state_fun = self.parse_status_headers
        else:
            self.state_error(line)

    def parse_status_headers(self, line):
        if line.startswith(b'IP  ') or line.startswith(b'^2IP   '):
            players_count = self.metrics.get('players_count')
            if players_count is not None and players_count > 0:
                self.players_count = players_count
                self.status_players = 0
                self.state_fun = self.parse_players_info
            else:
                self.done = True
                self.state_fun = None

    def parse_players_info(self, line):
        player_data = line.split()
        if len(player_data) < 5:
            # we received something strange
            error = "Received bad line, not enough fields: {0!r}".format(line)
            raise IllegalState(error)

        player_ip = self.strip_colors(player_data[0].strip())
        self.status_players += 1

        if self.status_players == self.players_count:
            self.done = True
            self.state_fun = None

        if player_ip == b'botclient':
            self.metrics['players_bots'] += 1

        try:
            score = int(player_data[4])
        except (ValueError, IndexError):
            raise IllegalState("Bad player score: {0!r}".format(line))

        if score == -666:
            self.metrics['players_spectators'] += 1
        else:
            self.metrics['players_active'] += 1

    @classmethod
    def strip_colors(cls, binary_data):
        return cls.COLORS_RE.sub(b'', binary_data)
