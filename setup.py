import glob
import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README')).read()

DATA = [
    ('etc', [f for f in glob.glob(os.path.join('etc', '*'))]),
    ('templates', [f for f in glob.glob(os.path.join('templates', '*'))]),
    ('res', [f for f in glob.glob(os.path.join('res', '*'))])
]

dependencies = [
    'jinja2',
    'six',
    'python-subunit',
    'testtools'
]

entry_points = {
    "console_scripts":
        "tparser = tempest_parser.tparser:tempest_cli_parser_main"
}


setup(
    name="TempestParser",
    version="0.2.47",
    author="Alex Savatieiev",
    author_email="a.savex@gmail.com",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7"
    ],
    keywords="QA, tempest, openstack, html, report",
    entry_points=entry_points,
    url="https://github.com/savex/tempest-parser",
    packages=find_packages(),
    include_package_data=True,
    package_data={
        '': ['*.conf', '*.list', '*.html']
    },
    zip_safe=False,
    install_requires=dependencies,
    data_files=DATA,
    license="Apache Licence, version 2",
    description="Tempest Parser tool used to generate trending reports "
                "out of various result formats openstack/tempest "
                "produces: pytest's CLI, Rally's JSON, CSV (two types) "
                "and Subunit (binary stream and XML export).",
    long_description=README
)
