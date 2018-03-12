from xonotic_exporter.metrics_parser import XonoticMetricsParser, IllegalState
import rcon_fixtures
import pytest


@pytest.fixture(scope="function")
def parser():
    return XonoticMetricsParser()


def test_valid_multiple(parser):
    for data in rcon_fixtures.RESPONSE1:
        parser.feed_data(data)

    assert parser.metrics['sv_public'] == 1
    assert parser.metrics['map'] == 'dissocia'
    assert parser.metrics['players_count'] == 15
    assert parser.done is True


def test_invalid_multiple(parser):
    with pytest.raises(IllegalState):
        for data in rcon_fixtures.UNORDERED_RESPONSE:
            parser.feed_data(data)


def test_valid_simple(parser):
    for data in rcon_fixtures.RESPONSE2:
        parser.feed_data(data)

    assert parser.metrics['sv_public'] == -1
    assert parser.metrics['map'] == 'xonwall'
    assert parser.metrics['players_count'] == 0
    assert parser.metrics['timing_cpu'] == pytest.approx(3.0, 0.1)
    assert parser.done is True


def test_parser_with_bots(parser):
    for data in rcon_fixtures.RESPONSE3:
        parser.feed_data(data)

    assert parser.metrics['sv_public'] == 1
    assert parser.metrics['players_count'] == 5
    assert parser.metrics['players_active'] == 0
    assert parser.metrics['players_spectators'] == 1
    assert parser.metrics['players_bots'] == 4
