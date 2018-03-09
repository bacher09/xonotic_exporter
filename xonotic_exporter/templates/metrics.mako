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
% if hostname is not UNDEFINED:
# hostname: ${hostname}
% endif
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
