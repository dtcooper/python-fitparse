#!/usr/bin/env python

import os
import sys

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest


TEST_PATH = os.path.join(os.path.realpath(os.path.dirname(__file__)), 'tests')

suite = unittest.defaultTestLoader.discover(start_dir=TEST_PATH)
runner = unittest.TextTestRunner()
runner.run(suite)
