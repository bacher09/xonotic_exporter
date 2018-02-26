from setuptools import setup


setup(
    name="xonotic_exporter",
    description="Xonotic metrics exporter for prometheus monitoring",
    author="Slava Bacherikov",
    author_email="slava@bacher09.org",
    packages=["xonotic_exporter"],
    include_package_data=True,
    install_requires=[
        "xrcon==0.1",
        "aiohttp>=3.0,<4.0",
        "mako>=1.0.0,<1.1.0",
        "jsonschema>=2.6.0,<2.7.0",
        "pyyaml"
    ],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Internet",
        "Topic :: Games/Entertainment",
        "Topic :: Games/Entertainment :: First Person Shooters",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)"
    ],
    entry_points="""\
    [console_scripts]
    xonotic_exporter = xonotic_exporter.cli:XonoticExporterCli.start
    """,
    platforms='any',
    keywords=[
        'rcon', 'xonotic', 'darkplaces', 'quake', 'nexuiz',
        'prometheus' 'nexuiz', 'metrics', 'monitoring'
    ],
    license="GPLv3",
    version="0.1dev"
)
