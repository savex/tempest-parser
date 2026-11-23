import glob
import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    README = f.read()

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
    version="0.3.0",
    author="Alex Savatieiev",
    author_email="a.savex@gmail.com",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.9"
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
                "out of various result formats: pytest's CLI, Rally's XML,"
                "JSON, jUnit XML (with v4 schema support), CSV (two types).",
    long_description=README,
    long_description_content_type="text/markdown"
)
