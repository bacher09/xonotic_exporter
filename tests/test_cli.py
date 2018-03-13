from xonotic_exporter import cli
import pytest
import argparse


BAD_CONFIG = """\
server:
  server: some.server
  port: 26000
"""


GOOD_CONFIG = """\
server:
  server: good.server
  rcon_password: "secret"
"""


def test_port_validator():
    with pytest.raises(argparse.ArgumentTypeError):
        cli.XonoticExporterCli.port_validator("test")

    with pytest.raises(argparse.ArgumentTypeError):
        cli.XonoticExporterCli.port_validator("0")

    with pytest.raises(argparse.ArgumentTypeError):
        cli.XonoticExporterCli.port_validator("-1")

    with pytest.raises(argparse.ArgumentTypeError):
        cli.XonoticExporterCli.port_validator("65536")

    assert cli.XonoticExporterCli.port_validator("26000") == 26000


def test_parse_config():
    exporter_cli = cli.XonoticExporterCli()
    with pytest.raises(cli.ConfigError):
        exporter_cli.parse_config("bad")

    with pytest.raises(cli.ConfigError):
        exporter_cli.parse_config("bad\0")

    with pytest.raises(cli.ConfigError):
        exporter_cli.parse_config(BAD_CONFIG)

    conf = exporter_cli.parse_config(GOOD_CONFIG)
    assert conf['server']['server'] == 'good.server'
    assert conf['server']['rcon_password'] == 'secret'


def test_configuration_provider(mocker):
    exporter_cli = cli.XonoticExporterCli()
    open_mock = mocker.mock_open(read_data=GOOD_CONFIG)
    mocker.patch('xonotic_exporter.cli.open', open_mock)
    conf = exporter_cli.parse_config(GOOD_CONFIG)
    provider = exporter_cli.build_configuration_provider(conf, 'test.yml')
    conf1 = provider()
    conf2 = provider()
    open_mock.assert_called_with("test.yml", "r")
    assert conf2['server']['server'] == conf1['server']['server']

    provider = exporter_cli.build_configuration_provider(conf, '<stdin>')
    assert provider() is not None
    assert provider() is None

    mocker.stopall()
    open_mock = mocker.Mock()
    open_mock.side_effect = PermissionError()
    mocker.patch('xonotic_exporter.cli.open', open_mock)
    provider = exporter_cli.build_configuration_provider(conf, 'test.yml')
    assert provider() is not None
    assert provider() is None

    mocker.stopall()
    open_mock = mocker.mock_open(read_data=BAD_CONFIG)
    mocker.patch('xonotic_exporter.cli.open', open_mock)
    provider = exporter_cli.build_configuration_provider(conf, 'test.yml')
    assert provider() is not None
    assert provider() is None
