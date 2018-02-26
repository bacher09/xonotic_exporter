import asyncio
import argparse
import jsonschema
import json
import yaml
import os
from .server import XonoticExporter


class XonoticExporterCli:

    DESCRIPTION = 'Xonotic prometheus exporter'
    DEFAULT_HOST = 'localhost'
    DEFAULT_PORT = 9260

    def __init__(self):
        self.parser = self.build_parser()
        self.config_schema = self.load_configuration_schema()

    def run(self, args=None):
        args = self.parser.parse_args(args)
        conf = self.parse_config(args.config)
        loop = asyncio.get_event_loop()
        exporter = XonoticExporter(loop, conf, host=args.host, port=args.port)
        exporter.run()

    def parse_config(self, conf_file):
        # TODO: display error on invalid yaml file
        config = yaml.load(conf_file.read())
        try:
            self.config_schema.validate(config)
        except jsonschema.ValidationError as exc:
            path = "/".join(exc.path)
            message = "{prog}: configuration error: {msg} at {path}\n".format(
                prog=self.parser.prog,
                msg=exc.message,
                path=path
            )
            self.parser.print_usage()
            self.parser.exit(os.EX_CONFIG, message)
        else:
            return config

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
