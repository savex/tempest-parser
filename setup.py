import os

from setuptools import setup, find_namespace_packages

here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.md'), encoding='utf-8') as f:
    README = f.read()

dependencies = [
    'jinja2',
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
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "Programming Language :: Python :: 3.15",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
    ],
    keywords="QA, tempest, openstack, kubernetes, pytest, subunit, html, report",
    entry_points=entry_points,
    url="https://github.com/savex/tempest-parser",
    project_urls={
        "Changelog": "https://github.com/savex/tempest-parser/blob/master/changelog.md",
        "Issues": "https://github.com/savex/tempest-parser/issues",
    },
    # etc/, res/ and templates/ hold data files only; listing them as namespace packages keeps
    # setuptools from warning that they are importable but not packaged
    packages=find_namespace_packages(include=["tempest_parser", "tempest_parser.*"]),
    include_package_data=True,
    package_data={
        '': ['*.conf', '*.list', '*.html']
    },
    zip_safe=False,
    python_requires=">=3.11",
    install_requires=dependencies,
    license="Apache-2.0",
    description="Builds trending HTML and CSV reports from Tempest, pytest, Rally, "
                "k8s conformance and subunit test results.",
    long_description=README,
    long_description_content_type="text/markdown"
)
