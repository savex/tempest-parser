import glob
import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.md')).read()

DATA = [
    ('etc', [f for f in glob.glob(os.path.join('etc', '*'))]),
    ('templates', [f for f in glob.glob(os.path.join('templates', '*'))]),
    ('res', [f for f in glob.glob(os.path.join('res', '*'))])
]

dependencies = [
    'six',
    'jinja2'
]

entry_points = {
    "console_scripts": "tparser = tempest_parser.tparser:main"
}


setup(
    name="TempestParser",
    version="0.1.2",
    author="Alex Savatieiev",
    author_email="a.savex@gmail.com",
    classifiers=[
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7"
    ],
    keywords="QA, tempest, openstack, html, report",
    entry_points=entry_points,
    url="https://github.com/osavatieiev/tempest-parser",
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=dependencies,
    data_files=DATA,
    license="Apache Licence, version 2",
    description="Tempest Parser tool used to generate trending reports "
                "out of various result formats openstack/tempest "
                "produces: CLI, JSON from Rally, XML from PyCharm, CSV",
    long_description=README
)

