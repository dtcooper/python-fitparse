# coding: utf-8
from distutils.core import setup

try:
    from setuptools import setup, find_packages, Command
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup, find_packages, Command

setup(
    name = "python-fitparse",
    version = "0.1",
    # scripts = ['scripts/generate_profile.py', 'scripts/sample_program.py'],
    zip_safe = True,
    packages = find_packages(),
    include_package_data = True,

    # metadata for upload to PyPI
    # author = "",
    # author_email = "",
    description = "Garmin FIT file parser implementation",
    # license = "",
    # keywords = "",
    url = "https://github.com/dtcooper/python-fitparse",

    # could also include long_description, download_url, classifiers, etc.
)

