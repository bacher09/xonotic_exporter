import pytest
from xonotic_exporter.server import XonoticExporter
from xrcon import utils as xon_utils
from prometheus_client.parser import text_string_to_metric_families
from test_xonotic import rcon_server  # noqa: F401
import rcon_fixtures


FAKE_CONFIG = {
    'server1': {
        'server': 'server1'
    },
    'server2': {
        'server': 'server2'
    },
    'server3': {
        'server': 'server3'
    }
}


FAKE_METRICS = {
    'server1': {
        'sv_public': 1,
        'players_count': 4,
        'players_active': 3,
        'players_spectators': 1,
        'players_bots': 0,
        'players_max': 10,
        'timing_cpu': 10,
        'timing_lost': 0.1,
        'timing_offset_avg': 0.2,
        'timing_max': 0.5,
        'timing_sdev': 0.1,
        'ping': 0.01,
        'hostname': 'Server 1'
    },
    'server2': {
        'sv_public': 1,
        'players_count': 4,
        'players_active': 3,
        'players_spectators': 1,
        'players_bots': 0,
        'players_max': 10,
        'timing_cpu': 10,
        'timing_offset_avg': 0.2,
        'timing_max': 0.5,
        'timing_sdev': 0.1,
        'ping': 0.01,
    },
    'server3': {
        'sv_public': 1,
    }
}


@pytest.fixture
def cli(loop, aiohttp_client, mocker):

    async def get_metrics(self, server_conf):
        return FAKE_METRICS[server_conf['server']]

    mocker.patch.object(XonoticExporter, 'get_metrics', new=get_metrics)
    exporter = XonoticExporter(loop, FAKE_CONFIG)
    return loop.run_until_complete(aiohttp_client(exporter.app))


async def test_main(cli):
    resp = await cli.get('/')
    assert resp.status == 200
    text = await resp.text()
    assert 'server1' in text
    assert 'server2' in text
    assert 'server3' in text


async def test_metrics(cli):
    prefix_len = len("xonotic_")
    resp = await cli.get('/metrics', params={"target": "server1"})
    assert resp.status == 200
    text = await resp.text()
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            name, labels, value = sample
            assert labels['instance'] == 'server1'
            metrics_name = name[prefix_len:]
            if metrics_name != 'rtt':
                assert value == FAKE_METRICS['server1'][metrics_name]

    resp2 = await cli.get('/metrics', params={"target": "server2"})
    assert resp2.status == 200
    resp3 = await cli.get('/metrics', params={"target": "server3"})
    assert resp3.status == 200
    text = await resp3.text()
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            name, labels, value = sample
            assert labels['instance'] == 'server3'
            if name == 'xonotic_sv_public':
                assert value == 1

    resp_inv = await cli.get('/metrics', params={"target": "server4"})
    assert resp_inv.status == 400

    resp_inv = await cli.get('/metrics')
    assert resp_inv.status == 400


async def test_get_metrics(rcon_server, loop):  # noqa: F811
    addr, port = rcon_server.endpoint
    server_conf = {
        'server': addr,
        'port': port,
        'rcon_password': 'test'
    }
    config = {'server': server_conf}

    def handle_rcon(data, addr):
        for rcon_chunk in rcon_fixtures.RESPONSE1:
            packet = xon_utils.RCON_RESPONSE_HEADER + rcon_chunk
            rcon_server.transport.sendto(packet, addr)

    rcon_server.handle_rcon = handle_rcon
    exporter = XonoticExporter(loop, config)
    metrics = await exporter.get_metrics(server_conf)
    assert metrics['map'] == 'dissocia'
    assert metrics['players_count'] == 15


async def test_server_reload(loop, aiohttp_client, mocker):
    provider_mock = mocker.Mock()
    provider_mock.return_value = FAKE_CONFIG
    exporter = XonoticExporter(loop, provider_mock)
    cli = await aiohttp_client(exporter.app)
    resp = await cli.post("/-/reload")
    assert resp.status == 200

    provider_mock.return_value = None
    resp = await cli.post("/-/reload")
    assert resp.status == 500

    exporter = XonoticExporter(loop, FAKE_CONFIG)
    cli = await aiohttp_client(exporter.app)
    resp = await cli.post("/-/reload")
    assert resp.status == 400
