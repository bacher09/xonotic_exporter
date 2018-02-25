import asyncio
import time
from xrcon import utils
import enum
import re


PING_Q2_PACKET = b"\xFF\xFF\xFF\xFFping"
PONG_Q2_PACKET = b"\xFF\xFF\xFF\xFFack"
COLORS_RE = re.compile(r"\^(?:\d|x[\dA-Fa-f]{3})")
# TODO: add logging


def strip_colors(text):
    return COLORS_RE.sub('', text)


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

    SV_PUBLIC_RE = re.compile(r'^"sv_public"\s+is\s+"(-?\d+)"')
    HOST_RE = re.compile(r'^host:\s+(.+)$')
    MAP_RE = re.compile('^map:\s+([^\s]+)')
    TIMING_RE = re.compile(
        r'^timing:\s+'
        r'(?P<cpu>-?[\d\.]+)%\s+CPU,\s+'
        r'(?P<lost>-?[\d\.]+)%\s+lost,\s+'
        r'offset\s+avg\s+(?P<offset_avg>-?[\d\.]+)ms,\s+'
        r'max\s+(?P<max>-?[\d\.]+)ms,\s+'
        r'sdev\s+(?P<sdev>-?[\d\.]+)ms'
    )
    PLAYERS_RE = re.compile(
        r'^players:\s+(?P<count>\d+)\s+active\s+\((?P<max>\d+)\s+max\)'
    )

    def __init__(self, loop, rcon_password, rcon_mode, retries_count=3,
                 timeout=3, read_timeout=0.4, initial_wait=0.8):
        super().__init__(loop, rcon_password, rcon_mode)
        self.retries_count = retries_count
        self.timeout = timeout
        self.read_timeout = read_timeout
        self.initial_wait = initial_wait

    async def rcon_read(self, read_timeout, initial_wait=1.0):
        await asyncio.sleep(initial_wait, loop=self.loop)
        val = b""
        while True:
            try:
                val += await asyncio.wait_for(
                    self.rcon_queue.get(),
                    read_timeout,
                    loop=self.loop
                )
            except asyncio.TimeoutError:
                return val

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
            result = await self.rcon_read(self.read_timeout, self.initial_wait)
            return self.parse_rcon_metrics(result)

        value = await self.retry(try_load_metrics)
        return value

    async def retry(self, async_fun, *args, **kwargs):
        for i in range(self.retries_count):
            try:
                task = async_fun(*args, **kwargs)
                value = await asyncio.wait_for(task, self.timeout,
                                               loop=self.loop)
            except OSError:
                continue
            else:
                return value

        raise RetryError("Retries limit exceeded")

    @classmethod
    def parse_rcon_metrics(cls, metrics_data):
        # TODO: Refactor this
        metrics = metrics_data.decode("utf8", "ignore").splitlines()
        handling_players = False
        start_players = False
        metrics_dct = {}
        metrics_dct['players_active'] = 0
        metrics_dct['players_spectators'] = 0
        metrics_dct['players_bots'] = 0
        for line in metrics:
            if start_players:
                if line.startswith('IP  ') or line.startswith('^2IP   '):
                    handling_players = True
                    start_players = False

                continue

            if handling_players:
                player_data = line.split()
                if len(player_data) < 5:
                    # we received something strange, let's ignore it
                    continue

                player_ip = strip_colors(player_data[0].strip())
                if player_ip == 'botclient':
                    metrics['players_bots'] += 1

                try:
                    score = int(player_data[4])
                except (ValueError, IndexError):
                    continue

                if score == -666:
                    metrics_dct['players_spectators'] += 1
                else:
                    metrics_dct['players_active'] += 1

                continue

            sv_public_m = cls.SV_PUBLIC_RE.match(line)
            if sv_public_m is not None:
                val = sv_public_m.group(1)
                try:
                    val = int(val)
                except ValueError:
                    pass
                else:
                    metrics_dct['sv_public'] = val

                continue

            host_m = cls.HOST_RE.match(line)
            if host_m is not None:
                val = host_m.group(1).strip()
                metrics_dct['hostname'] = val
                continue

            map_m = cls.MAP_RE.match(line)
            if map_m is not None:
                val = map_m.group(1)
                metrics_dct['map'] = val
                continue

            timing_m = cls.TIMING_RE.match(line)
            if timing_m is not None:
                vals = timing_m.groupdict()
                for key, val in vals.items():
                    try:
                        val = float(val)
                    except ValueError:
                        pass
                    else:
                        metrics_dct["timing_{0}".format(key)] = val

                continue

            players_m = cls.PLAYERS_RE.match(line)
            if players_m is not None:
                for key, val in players_m.groupdict().items():
                    try:
                        val = int(val)
                    except ValueError:
                        pass
                    else:
                        metrics_dct["players_{0}".format(key)] = val

                start_players = True
                continue

        return metrics_dct
