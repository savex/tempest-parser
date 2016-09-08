from distutils.core import setup

setup(
    name="TempestParser",
    version="0.1",
    author="Alex Savatieiev",
    author_email="a.savex@gmail.com",
    entry_points={
        "console_scripts":
            ["tparser = tempest_parser.tparser:main"]
    },
    url="https://github.com/osavatieiev/tempest-parser",
    packages=['tempest_parser',],
    license="Apache Licence, version 2",
    description="Parser of tempest results.",
    long_description="Tempest Parser tool used to generate trending reports "
                     "out of various result formats openstack/tempest "
                     "produces: CLI, JSON from Rally, XML from PyCharm, CSV"
)
