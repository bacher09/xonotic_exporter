from setuptools import setup
import os.path


ROOT_PATH = os.path.dirname(__file__)
with open(os.path.join(ROOT_PATH, "README.rst")) as f:
    long_description = f.read()


setup(
    name="xonotic_exporter",
    description="Xonotic metrics exporter for prometheus monitoring",
    long_description=long_description,
    author="Slava Bacherikov",
    author_email="slava@bacher09.org",
    url="https://github.com/bacher09/xonotic_exporter",
    packages=["xonotic_exporter"],
    include_package_data=True,
    install_requires=[
        "xrcon==0.1",
        "aiohttp>=3.0,<4.0",
        "mako>=1.0.0,<1.1.0",
        "jsonschema>=3.0.1,<3.1.0",
        "pyyaml"
    ],
    tests_require=[
        'pytest',
        'pytest-cov',
        'pytest-aiohttp',
        'pytest-mock',
        'prometheus_client>=0.7.1,<0.8'
    ],
    setup_requires=['pytest-runner'],
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
    version="0.2dev"
)
