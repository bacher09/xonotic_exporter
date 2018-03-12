from xonotic_exporter import xonotic
from xrcon import utils as xon_utils
import rcon_fixtures
import asyncio
import pytest


TEST_TIMEOUT = 0.1
NONSECURE_RCON_HEADER = xon_utils.RCON_PACKET_HEADER + b"rcon "
SECURE_RCON_HEADER = xon_utils.RCON_PACKET_HEADER + b"srcon "


class FakeRconServer:

    CHALLENGE = b'challenge01'

    def __init__(self, loop, rtt_delay=0.01):
        self.loop = loop
        self.rtt_delay = rtt_delay
        self.endpoint = None
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        self.endpoint = self.transport.get_extra_info('sockname')

    def datagram_received(self, data, addr):
        if data == xonotic.PING_Q2_PACKET:
            self.ping_received(addr)
        elif data == xon_utils.CHALLENGE_PACKET:
            self.getchallenge_received(addr)
        elif data.startswith(NONSECURE_RCON_HEADER):
            self.handle_rcon(data, addr)
        elif data.startswith(SECURE_RCON_HEADER):
            self.handle_rcon(data, addr)

    def error_received(self, exc):
        pass

    def connection_lost(self, exc):
        pass

    def ping_received(self, addr):
        def respond():
            self.transport.sendto(xonotic.PONG_Q2_PACKET, addr)

        self.loop.call_later(self.rtt_delay, respond)

    def getchallenge_received(self, addr):
        packet = xon_utils.CHALLENGE_RESPONSE_HEADER + self.CHALLENGE
        self.transport.sendto(packet, addr)

    def handle_rcon(self, data, addr):
        pass


@pytest.fixture
async def rcon_server(loop):

    def rcon_factory():
        return FakeRconServer(loop)

    transport, proto = await loop.create_datagram_endpoint(
        rcon_factory, local_addr=('127.0.0.1', 0)
    )
    return proto


@pytest.fixture
async def xonotic_proto(loop, rcon_server):

    def proto_factory():
        return xonotic.XonoticProtocol(loop, "password", 0)

    transport, proto = await loop.create_datagram_endpoint(
        proto_factory, remote_addr=rcon_server.endpoint
    )
    return proto


@pytest.fixture
async def xonotic_metrics_proto(loop, rcon_server):

    def proto_factory():
        return xonotic.XonoticMetricsProtocol(loop, "password", 0)

    transport, proto = await loop.create_datagram_endpoint(
        proto_factory, remote_addr=rcon_server.endpoint
    )
    return proto


async def test_ping(xonotic_proto, loop):
    rtt = await asyncio.wait_for(xonotic_proto.ping(), TEST_TIMEOUT, loop=loop)
    assert rtt < 1


async def test_getchallenge(xonotic_proto, loop):
    challenge = await asyncio.wait_for(
        xonotic_proto.getchallenge(),
        TEST_TIMEOUT,
        loop=loop
    )
    assert challenge == FakeRconServer.CHALLENGE


async def test_rcon(xonotic_proto, rcon_server, loop, mocker):
    rcon_server.handle_rcon = mocker.Mock()

    xonotic_proto.set_mode(0)
    await asyncio.wait_for(
        xonotic_proto.rcon(b"status 1"),
        TEST_TIMEOUT,
        loop=loop
    )
    assert b'rcon' in rcon_server.handle_rcon.call_args[0][0]
    assert b'status 1' in rcon_server.handle_rcon.call_args[0][0]
    rcon_server.handle_rcon.reset_mock()

    xonotic_proto.set_mode(1)
    await asyncio.wait_for(
        xonotic_proto.rcon(b"status 1"),
        TEST_TIMEOUT,
        loop=loop
    )
    assert b'srcon HMAC-MD4 TIME' in rcon_server.handle_rcon.call_args[0][0]
    assert b'status 1' in rcon_server.handle_rcon.call_args[0][0]

    xonotic_proto.set_mode(2)
    await asyncio.wait_for(
        xonotic_proto.rcon(b"status 1"),
        TEST_TIMEOUT,
        loop=loop
    )
    assert b'srcon HMAC-MD4 CHALLENGE' in \
        rcon_server.handle_rcon.call_args[0][0]
    assert b'status 1' in rcon_server.handle_rcon.call_args[0][0]


async def test_rcon_metrics(xonotic_metrics_proto, rcon_server):

    def handle_rcon(data, addr):
        for rcon_chunk in rcon_fixtures.RESPONSE1:
            packet = xon_utils.RCON_RESPONSE_HEADER + rcon_chunk
            rcon_server.transport.sendto(packet, addr)

    rcon_server.handle_rcon = handle_rcon
    rcon_metrics = await xonotic_metrics_proto.get_rcon_metrics()
    assert rcon_metrics['map'] == 'dissocia'
    assert rcon_metrics['players_count'] == 15
    assert rcon_metrics['players_max'] == 20
    assert rcon_metrics['players_spectators'] == 5


async def test_ping_retry(xonotic_metrics_proto, rcon_server):
    real_ping_handler = rcon_server.ping_received
    ping_counter = 0

    def ping_received(addr):
        nonlocal ping_counter
        ping_counter += 1

        if ping_counter % 3 == 0:  # responding to every 3rd packet
            real_ping_handler(addr)

    rcon_server.ping_received = ping_received
    # decrease ping timeout, so tests will take less time
    xonotic_metrics_proto.timeout = rcon_server.rtt_delay * 2
    rtt = await xonotic_metrics_proto.ping()
    assert rtt < 1


async def test_metrics(xonotic_metrics_proto, rcon_server):

    def handle_rcon(data, addr):
        for rcon_chunk in rcon_fixtures.RESPONSE1:
            packet = xon_utils.RCON_RESPONSE_HEADER + rcon_chunk
            rcon_server.transport.sendto(packet, addr)

    rcon_server.handle_rcon = handle_rcon
    # decrease ping timeout, so tests will take less time
    xonotic_metrics_proto.timeout = rcon_server.rtt_delay * 2
    metrics = await xonotic_metrics_proto.get_metrics()
    assert metrics['ping'] < 1
    assert metrics['map'] == 'dissocia'


async def test_retry_limit(xonotic_metrics_proto, rcon_server):

    def ping_received(addr):
        pass

    rcon_server.ping_received = ping_received
    xonotic_metrics_proto.timeout = 0.001
    with pytest.raises(xonotic.RetryError):
        await xonotic_metrics_proto.ping()


def test_set_mode(mocker):
    xon_proto = xonotic.XonoticProtocol(mocker.Mock(), "test", 0)

    with pytest.raises(ValueError):
        xon_proto.set_mode(10)

    with pytest.raises(ValueError):
        xon_proto.set_mode(-1)

    with pytest.raises(ValueError):
        xon_proto.set_mode("bad")
