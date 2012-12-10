from distutils.core import setup

setup(
    name='fitparse',
    version='0.1.0-dev',
    description='Python library to parse ANT/Garmin .FIT files',
    author='David Cooper',
    author_email='dave@kupesoft.com',
    url='http://www.github.com/dtcooper/python-fitparse',
    license=open('LICENSE').read(),
    packages=['fitparse'],
    scripts=['scripts/fitdump'],  # Don't include generate_profile.py
)
