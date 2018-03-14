xonotic_exporter
================

.. image:: https://travis-ci.org/bacher09/xonotic_exporter.svg?branch=master
    :target: https://travis-ci.org/bacher09/xonotic_exporter

.. image:: https://ci.appveyor.com/api/projects/status/github/bacher09/xonotic_exporter?svg=true&branch=master
    :target: https://ci.appveyor.com/project/bacher09/xonotic-exporter

.. image:: https://coveralls.io/repos/bacher09/xonotic_exporter/badge.svg?branch=master
    :target: https://coveralls.io/r/bacher09/xonotic_exporter?branch=master 


Xonotic metrics exporter for `Prometheus monitoring system`_.
Metrics are obtained by querying server via rcon (``status 1`` command).

Installation
------------

  * execute ``pip install xonotic_exporter``
  * or run ``pip install -e git+https://github.com/bacher09/xonotic_exporter#egg=xonotic_exporter``
    to install latest development version from github


Configuration
-------------

Xonotic exporter is configured by file and CLI options. CLI options is used to
specify which port or address to listen, what configuration to use and
configuration file is used to specify servers from where metrics will be
exported. Configuration file is YAML dictionary, where keys are server names
(`instance` label in prometheus) and values are server connection options.
Here's example configuration::

  public:
    server: 172.16.254.1
    port: 26000
    rcon_password: "secretpassword"
    rcon_mode: 1
  private:
    server: private.example.com
    rcon_password: "secret"
  ipv6-server:
    server: 2001:db8:85a3::8a2e:370:7334
    port: 26001
    rcon_mode: 2
    rcon_password: "password"


Connection options have few required fields (``server``, ``rcon_password``) and
also some optional fields (``port``, ``rcon_mode``) which have default value.
`server` field might contain IPv4 or IPv6 address or DNS name. If you are using
DNS name, it will be resolved each time before making request to server, so if
you change DNS record you don't need to restart exporter to use new IP.
For more info about configuration file format you can check `it's JSON schema`__.
Also, you can check correctness of configuration using ``--validate`` CLI option.

__ json_schema_

If you edit configuration file, you can update configuration without restarting
Xonotic exporter, just send ``HUP`` signal to process or send POST request to
``/-/reload`` endpoint.

For example::

  $ kill -HUP 4429   # 4429 is exporters PID
  $ curl -XPOST http://localhost:9260/-/reload


Prometheus Configuration
------------------------

The exporter needs server name to be passed as target parameter. It similar to
blackbox_ and snmp_ exporters.

Example prometheus configuration::

  scrape_configs:
    - job_name: 'xonotic_exporter'
      relabel_configs:
        - source_labels: [__address__]
          target_label: __param_target
        - source_labels: [__param_target]
          target_label: instance
        - target_label: __address__
          replacement: 127.0.0.1:9260
      static_configs:
        - targets: ['public', 'private', 'ipv6-server']  # server names


.. _`Prometheus monitoring system`: https://prometheus.io/
.. _json_schema: https://github.com/bacher09/xonotic_exporter/blob/master/xonotic_exporter/config_schema.json
.. _blackbox: https://github.com/prometheus/blackbox_exporter
.. _snmp: https://github.com/prometheus/snmp_exporter
