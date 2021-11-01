from distutils.core import setup
import sys

import fitparse


requires = None
if sys.version_info < (2, 7) or (3, 0) <= sys.version_info < (3, 3):
    sys.exit("Python 2.7 or Python 3.3+ are required.")


setup(
    name='fitparse',
    version=fitparse.__version__,
    description='Python library to parse ANT/Garmin .FIT files',
    author='David Cooper',
    author_email='dave@kupesoft.com',
    url='https://www.github.com/dtcooper/python-fitparse',
    license=open('LICENSE').read(),
    packages=['fitparse'],
    scripts=['scripts/fitdump'],  # Don't include generate_profile.py
    install_requires=requires,
)
