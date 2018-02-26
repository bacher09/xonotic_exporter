import asyncio
import os.path
from mako.lookup import TemplateLookup
from aiohttp import web
from .xonotic import XonoticMetricsProtocol


class XonoticExporter:

    CONFIG_DEFAULT_PORT = 26000
    CONFIG_DEFAULT_RCON_MODE = 1

    def __init__(self, loop, servers_config, host='127.0.0.1', port=9260):
        self.loop = loop
        self.config = servers_config
        self.host = host
        self.port = port
        self.app = web.Application()
        self.init_templates()
        self.init_routes()

    def init_templates(self):
        self.mako_lookup = TemplateLookup(self.templates_path(),
                                          filesystem_checks=False)

        self.index_template = self.mako_lookup.get_template('index.mako')
        self.metrics_template = self.mako_lookup.get_template('metrics.mako')

    def init_routes(self):
        self.app.router.add_get('/', self.root_handler)
        self.app.router.add_get('/metrics/{server}', self.metrics_handler)
        self.app.router.add_get('/metrics/', self.redirect_handler)

    async def root_handler(self, request):
        servers = sorted(self.config.keys())
        main = self.index_template.render(servers=servers)
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
        page = self.metrics_template.render(server=server, **metrics)
        return web.Response(text=page, content_type="text/plain")

    async def get_metrics(self, server):
        server_conf = self.config[server]
        host = server_conf['server']
        addr = (host, server_conf.get('port', self.CONFIG_DEFAULT_PORT))
        rcon_mode = server_conf.get('rcon_mode', self.CONFIG_DEFAULT_RCON_MODE)

        def proto_builder():
            return XonoticMetricsProtocol(
                loop=self.loop,
                rcon_password=server_conf['rcon_password'],
                rcon_mode=rcon_mode
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

    @staticmethod
    def templates_path():
        base_path = os.path.dirname(__file__)
        return os.path.join(base_path, 'templates')
