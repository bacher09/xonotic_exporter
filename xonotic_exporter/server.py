import asyncio
import argparse
from mako.template import Template
from aiohttp import web
import yaml
from .xonotic import XonoticMetricsProtocol


MAIN_TEMPLATE = Template("""\
<html>
    <head><title>Xonotic Exporter</title></head>
    <body>
        <h1>Xonotic Exporter</h1>
        <ul>
            % for server in servers:
                <li><a href="/metrics/${server | u}">${server | h}</a></li>
            % endfor
        </ul>
    </body>
</html>
""")


METRICS_TEMPLATE = Template("""\
<%!
    import socket

    def quotes(text):
        val = text.replace('"', '\\"')
        return '"{0}"'.format(val)

    def metric(val):
        if val is UNDEFINED or not isinstance(val, (int, float)):
            return 'NaN'
        else:
            return val

    current_host = socket.getfqdn()
%>
# server: ${server}
# hostname: ${hostname}
# map: ${map}
xonotic_sv_public{instance=${server | quotes}} ${metric(sv_public)}

# Players info
xonotic_players_count{instance=${server | quotes}} ${metric(players_count)}
xonotic_players_max{instance=${server | quotes}} ${metric(players_max)}
xonotic_players_bots{instance=${server | quotes}} ${metric(players_bots)}
xonotic_players_spectators{instance=${server | quotes}} ${metric(players_spectators)}
xonotic_players_active{instance=${server | quotes}} ${metric(players_active)}

# Performance timings
xonotic_timing_cpu{instance=${server | quotes}} ${metric(timing_cpu)}
xonotic_timing_lost{instance=${server | quotes}} ${metric(timing_lost)}
xonotic_timing_offset_avg{instance=${server | quotes}} ${metric(timing_offset_avg)}
xonotic_timing_max{instance=${server | quotes}} ${metric(timing_max)}
xonotic_timing_sdev{instance=${server | quotes}} ${metric(timing_sdev)}

# Network rtt
xonotic_rtt{instance=${server | quotes}, from=${current_host | quotes}} ${metric(ping)}
""")


class XonoticExporter:

    def __init__(self, loop, servers_config, host='127.0.0.1', port=9260):
        self.loop = loop
        self.config = servers_config
        self.host = host
        self.port = port
        self.app = web.Application()
        self.init_routes()

    def init_routes(self):
        self.app.router.add_get('/', self.root_handler)
        self.app.router.add_get('/metrics/{server}', self.metrics_handler)
        self.app.router.add_get('/metrics/', self.redirect_handler)

    async def root_handler(self, request):
        servers = sorted(self.config.keys())
        main = MAIN_TEMPLATE.render(servers=servers)
        return web.Response(text=main, content_type="text/html")

    async def redirect_handler(self, request):
        return web.HTTPFound('/')

    async def metrics_handler(self, request):
        server = request.match_info.get('server')
        if server is None:
            # "Server is empty"
            raise web.HTTPInternalServerError()

        if server not in self.config:
            # "There is no such server in config"
            return web.HTTPNotFound()

        metrics = await self.get_metrics(server)
        page = METRICS_TEMPLATE.render(server=server, **metrics)
        return web.Response(text=page, content_type="text/plain")

    async def get_metrics(self, server):
        server_conf = self.config[server]
        host = server_conf['server']
        addr = (host, server_conf['port'])

        def proto_builder():
            return XonoticMetricsProtocol(
                loop=self.loop,
                addr=addr,
                rcon_password=server_conf['rcon_password'],
                rcon_mode=server_conf['rcon_mode']
            )

        connection_task = self.loop.create_datagram_endpoint(
            proto_builder, remote_addr=addr
        )
        transport, proto = await connection_task
        metrics = await proto.get_metrics()
        transport.close()
        return metrics

    def run(self):
        return web.run_app(self.app, host=self.host, port=self.port)


class XonoticExporterCli:

    DESCRIPTION = 'Xonotic prometheus exporter'
    DEFAULT_HOST = 'localhost'
    DEFAULT_PORT = 9260

    def __init__(self):
        self.parser = self.build_parser()

    def run(self, args=None):
        args = self.parser.parse_args(args)
        conf = self.parse_config(args.config)
        loop = asyncio.get_event_loop()
        exporter = XonoticExporter(loop, conf, host=args.host, port=args.port)
        exporter.run()

    def parse_config(self, conf_file):
        # TODO: Add json schema validation
        return yaml.load(conf_file.read())

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
