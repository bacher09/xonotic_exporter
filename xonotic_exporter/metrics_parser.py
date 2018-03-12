import re


class IllegalState(ValueError):
    pass


class XonoticMetricsParser:

    COLORS_RE = re.compile(b"\^(?:\d|x[\dA-Fa-f]{3})")
    SV_PUBLIC_RE = re.compile(b'^"sv_public"\s+is\s+"(-?\d+)"')
    HOST_RE = re.compile(b'^host:\s+(.+)$')
    MAP_RE = re.compile(b'^map:\s+([^\s]+)')
    TIMING_RE = re.compile(
        b'^timing:\s+'
        b'(?P<cpu>-?[\d\.]+)%\s+CPU,\s+'
        b'(?P<lost>-?[\d\.]+)%\s+lost,\s+'
        b'offset\s+avg\s+(?P<offset_avg>-?[\d\.]+)ms,\s+'
        b'max\s+(?P<max>-?[\d\.]+)ms,\s+'
        b'sdev\s+(?P<sdev>-?[\d\.]+)ms'
    )
    PLAYERS_RE = re.compile(
        b'^players:\s+(?P<count>\d+)\s+active\s+\((?P<max>\d+)\s+max\)'
    )

    def __init__(self):
        self.state_fun = self.parse_sv_public
        self.done = False
        self.players_count = None
        self.status_players = None
        self.metrics = {}
        self.metrics['players_active'] = 0
        self.metrics['players_spectators'] = 0
        self.metrics['players_bots'] = 0
        self.old_data = b""

    def feed_data(self, binary_data):
        data = self.old_data + binary_data
        while not self.done:
            try:
                binary_line, data = data.split(b'\n', 1)
            except ValueError:
                # not enough data for unpacking
                self.old_data = data
                return
            else:
                self.process_line(binary_line)

    def process_line(self, line):
        if not self.done:
            self.state_fun(line)
        else:
            self.state_error(line)

    def state_error(self, line):
        # TODO: add more info about state
        raise IllegalState("Received bad input")

    def parse_sv_public(self, line):
        sv_public_m = self.SV_PUBLIC_RE.match(line)
        if sv_public_m is not None:
            val = sv_public_m.group(1)
            try:
                val = int(val)
            except ValueError:
                pass
            else:
                self.metrics['sv_public'] = val

            self.state_fun = self.parse_hostname  # update state
        else:
            self.state_error(line)

    def parse_hostname(self, line):
        host_m = self.HOST_RE.match(line)
        if host_m is not None:
            val = host_m.group(1).strip()
            self.metrics['hostname'] = val.decode("utf8", "ignore")
            self.state_fun = self.parse_version
        else:
            self.state_error(line)

    def parse_version(self, line):
        if line.startswith(b"version:"):
            self.state_fun = self.parse_protocol
        else:
            self.state_error(line)

    def parse_protocol(self, line):
        if line.startswith(b"protocol:"):
            self.state_fun = self.parse_map
        else:
            self.state_error(line)

    def parse_map(self, line):
        map_m = self.MAP_RE.match(line)
        if map_m is not None:
            val = map_m.group(1)
            self.metrics['map'] = val.decode("utf8", "ignore")
            self.state_fun = self.parse_timing
        else:
            self.state_error(line)

    def parse_timing(self, line):
        timing_m = self.TIMING_RE.match(line)
        if timing_m is not None:
            vals = timing_m.groupdict()
            for key, val in vals.items():
                try:
                    val = float(val)
                except ValueError:
                    pass
                else:
                    self.metrics["timing_{0}".format(key)] = val

            self.state_fun = self.parse_players
        else:
            self.state_error(line)

    def parse_players(self, line):
        players_m = self.PLAYERS_RE.match(line)
        if players_m is not None:
            for key, val in players_m.groupdict().items():
                try:
                    val = int(val)
                except ValueError:
                    pass
                else:
                    self.metrics["players_{0}".format(key)] = val

            self.state_fun = self.parse_status_headers
        else:
            self.state_error(line)

    def parse_status_headers(self, line):
        if line.startswith(b'IP  ') or line.startswith(b'^2IP   '):
            players_count = self.metrics.get('players_count')
            if players_count is not None and players_count > 0:
                self.players_count = players_count
                self.status_players = 0
                self.state_fun = self.parse_players_info
            else:
                self.done = True
                self.state_fun = None

    def parse_players_info(self, line):
        player_data = line.split()
        if len(player_data) < 5:
            # we received something strange
            error = "Received bad line, not enough fields: {0!r}".format(line)
            raise IllegalState(error)

        player_ip = self.strip_colors(player_data[0].strip())
        self.status_players += 1

        if self.status_players == self.players_count:
            self.done = True
            self.state_fun = None

        if player_ip == b'botclient':
            self.metrics['players_bots'] += 1
            return

        try:
            score = int(player_data[4])
        except (ValueError, IndexError):
            raise IllegalState("Bad player score: {0!r}".format(line))

        if score == -666:
            self.metrics['players_spectators'] += 1
        else:
            self.metrics['players_active'] += 1

    @classmethod
    def strip_colors(cls, binary_data):
        return cls.COLORS_RE.sub(b'', binary_data)
