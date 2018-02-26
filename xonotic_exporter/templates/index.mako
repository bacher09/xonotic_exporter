<html>
    <head>
        <title>Xonotic Exporter</title>
    </head>
    <body>
        <h1>Xonotic Exporter</h1>
        <ul>
            % for server in servers:
                <li><a href="/metrics?target=${server | u}">${server | h}</a></li>
            % endfor
        </ul>
    </body>
</html>
