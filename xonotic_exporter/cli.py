import asyncio
import argparse
import jsonschema
import json
import yaml
import os
import logging
from .server import XonoticExporter


log = logging.getLogger(__name__)


class ConfigError(ValueError):
    pass


class InvalidYamlConfig(ConfigError):
    pass


class InvalidYamlSchema(ConfigError):
    pass


class XonoticExporterCli:

    DESCRIPTION = 'Xonotic prometheus exporter'
    DEFAULT_HOST = 'localhost'
    DEFAULT_PORT = 9260
    exporter_factory = XonoticExporter

    def __init__(self):
        self.parser = self.build_parser()
        self.config_schema = self.load_configuration_schema()

    def run(self, args=None):
        args = self.parser.parse_args(args)

        try:
            with args.config as stream:
                config = self.parse_config(stream)
        except ConfigError as exc:
            message = "{prog}: configuration error: {msg}\n".format(
                prog=self.parser.prog, msg=str(exc)
            )
            self.parser.exit(os.EX_CONFIG, message)

        if args.validate:
            print("Configuration is correct")
            return

        conf_provider = self.build_configuration_provider(config,
                                                          args.config.name)
        loop = asyncio.get_event_loop()
        exporter = self.exporter_factory(loop, conf_provider, host=args.host,
                                         port=args.port)
        exporter.run()

    def parse_config(self, str_or_stream):
        try:
            config = yaml.load(str_or_stream)
        except yaml.YAMLError as exc:
            raise InvalidYamlConfig('Invalid yaml document') from exc

        if not isinstance(config, dict):
            raise InvalidYamlSchema("yaml should start as object")

        try:
            self.config_schema.validate(config)
        except jsonschema.ValidationError as exc:
            path = "/".join(exc.path)
            message = "{msg} at {path}".format(msg=exc.message, path=path)
            raise InvalidYamlSchema(message) from exc
        else:
            return config

    def build_configuration_provider(self, config, file_path):

        def load_conf():
            if file_path == '<stdin>':
                log.info("Can't reload config from stdin")
                return

            try:
                with open(file_path, "r") as conf_file:
                    return self.parse_config(conf_file)
            except ConfigError as exc:
                log.error("Can't parse configuration: %s", exc)
            except OSError as exc:
                log.error("Can't read file: %s}", exc)

        def provider_gen():
            nonlocal config
            yield config

            while True:
                yield load_conf()

        conf_iterator = provider_gen()
        return lambda: next(conf_iterator)

    @staticmethod
    def port_validator(port_str):
        try:
            port_val = int(port_str)
        except ValueError:
            raise argparse.ArgumentTypeError("port should be integer")
        else:
            if 0 < port_val <= 65535:
                return port_val
            else:
                msg = 'Port should be in range (0, 65535]'
                raise argparse.ArgumentTypeError(msg)

    @classmethod
    def build_parser(cls):
        parser = argparse.ArgumentParser(description=cls.DESCRIPTION)
        parser.add_argument('-l', '--listen-host', default=cls.DEFAULT_HOST,
                            dest='host', help='listen addr')
        parser.add_argument('-p', '--port', type=cls.port_validator,
                            default=cls.DEFAULT_PORT, help='listen port')
        parser.add_argument('--validate', action='store_true',
                            help='Only validate configuration')
        parser.add_argument('config', type=argparse.FileType())
        return parser

    @classmethod
    def start(cls):
        obj = XonoticExporterCli()
        obj.run()

    @staticmethod
    def load_configuration_schema():
        path = os.path.dirname(__file__)
        schema_path = os.path.join(path, 'config_schema.json')
        with open(schema_path, "r") as f:
            schema_json = json.load(f)

        return jsonschema.Draft4Validator(
            schema_json,
            format_checker=jsonschema.FormatChecker()
        )
