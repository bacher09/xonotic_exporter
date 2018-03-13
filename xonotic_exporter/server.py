import os.path
import signal
import logging
from mako.lookup import TemplateLookup
from aiohttp import web
from .xonotic import XonoticMetricsProtocol


log = logging.getLogger(__name__)


class XonoticExporter:

    CONFIG_DEFAULT_PORT = 26000
    CONFIG_DEFAULT_RCON_MODE = 1

    def __init__(self, loop, config_provider, host='127.0.0.1', port=9260):
        self.loop = loop

        if callable(config_provider):
            self.config = config_provider()
            self.config_provider = config_provider
        else:
            self.config = config_provider
            self.config_provider = None

        self.host = host
        self.port = port
        self.app = web.Application()
        self.init_templates()
        self.init_routes()

        if hasattr(loop, 'add_signal_handler') and hasattr(signal, 'SIGHUP'):
            loop.add_signal_handler(signal.SIGHUP, self.reload)

    def init_templates(self):
        self.mako_lookup = TemplateLookup(self.templates_path(),
                                          filesystem_checks=False)

        self.index_template = self.mako_lookup.get_template('index.mako')
        self.metrics_template = self.mako_lookup.get_template('metrics.mako')

    def init_routes(self):
        self.app.router.add_get('/', self.root_handler)
        self.app.router.add_get('/metrics', self.metrics_handler)
        self.app.router.add_post('/-/reload', self.reload_handler)

    async def root_handler(self, request):
        servers = sorted(self.config.keys())
        main = self.index_template.render(servers=servers)
        return web.Response(text=main, content_type="text/html")

    async def metrics_handler(self, request):
        server = request.query.get('target')
        if server is None:
            return web.Response(text="'target' parameter must be specified",
                                status=400, content_type="text/plain")

        server_conf = self.config.get(server)
        if server_conf is None:
            msg = "there is no such server in configuration: {0!r}" \
                    .format(server)
            return web.Response(text=msg, status=400,
                                content_type="text/plain")

        metrics = await self.get_metrics(server_conf)
        page = self.metrics_template.render(server=server, **metrics)
        return web.Response(text=page, content_type="text/plain")

    async def reload_handler(self, request):
        status = self.reload()
        if status is None:
            return web.Response(text="Configuration reloading isn't supported",
                                status=400, content_type="text/plain")
        elif status:
            return web.Response(text="Success", content_type="text/plain")
        else:
            return web.Response(text="Error", status=500,
                                content_type="text/plain")

    async def get_metrics(self, server_conf):
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

    def reload(self):
        "Reload server configuration"
        if self.config_provider is None:
            log.info("Configuration reloading isn't supported, "
                     "no configuration provider ")
            return

        new_configuration = self.config_provider()
        if new_configuration is not None:
            self.config = new_configuration
            log.info("Configuration reload successful")
            return True
        else:
            log.error("Can't reload configuration")
            return False

    def run(self):
        return web.run_app(self.app, host=self.host, port=self.port)

    @staticmethod
    def templates_path():
        base_path = os.path.dirname(__file__)
        return os.path.join(base_path, 'templates')
