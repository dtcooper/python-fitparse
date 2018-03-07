#!/usr/bin/env python
import datetime
import io
import os
import sys
import tempfile

from fitparse import utils
from fitparse.utils import fileish_open, is_iterable

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest


def testfile(filename):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'files', filename)


class UtilsTestCase(unittest.TestCase):

    def test_fit_to_datetime(self):
        sec = 3600 + 60 + 1
        dt = datetime.datetime(1989, 12, 31, 1, 1, 1)
        self.assertEqual(dt, utils.fit_from_datetime(sec))
        self.assertEqual(sec, utils.fit_to_datetime(dt))

    def test_fit_semicircles_to_deg(self):
        sc = 495280430
        deg = 41.513926070183516
        self.assertEqual(deg, utils.fit_semicircles_to_deg(sc))
        self.assertEqual(sc, utils.fit_deg_to_semicircles(deg))
        # test rounding errors
        for i in range(100):
            sc += 1
            self.assertEqual(sc, utils.fit_deg_to_semicircles(utils.fit_semicircles_to_deg(sc)))

    def test_fileish_open_read(self):
        """Test the constructor does the right thing when given different types
        (specifically, test files with 8 characters, followed by an uppercase.FIT
        extension), which confused the fileish check on Python 2, see
        https://github.com/dtcooper/python-fitparse/issues/29#issuecomment-312436350
        for details"""

        def test_fopen(fileish):
            with fileish_open(fileish, 'rb') as f:
                self.assertIsNotNone(f.read(1))
                f.seek(0, os.SEEK_SET)

        test_fopen(testfile('nametest.FIT'))
        with open(testfile("nametest.FIT"), 'rb') as f:
            test_fopen(f)
        with open(testfile("nametest.FIT"), 'rb') as f:
            test_fopen(f.read())
        with open(testfile("nametest.FIT"), 'rb') as f:
            test_fopen(io.BytesIO(f.read()))

    def test_fileish_open_write(self):

        def test_fopen(fileish):
            with fileish_open(fileish, 'wb') as f:
                f.write(b'\x12')
                f.seek(0, os.SEEK_SET)

        tmpfile = tempfile.NamedTemporaryFile(prefix='fitparse-test', suffix='.FIT', delete=False)
        filename = tmpfile.name
        tmpfile.close()
        try:
            test_fopen(filename)
            with open(filename, 'wb') as f:
                test_fopen(f)
            test_fopen(io.BytesIO())
        finally:
            # remove silently
            try:
                os.remove(filename)
            except OSError:
                pass

    def test_is_iterable(self):
        self.assertFalse(is_iterable(None))
        self.assertFalse(is_iterable(1))
        self.assertFalse(is_iterable('1'))
        self.assertFalse(is_iterable(b'1'))

        self.assertTrue(is_iterable((1, 2)))
        self.assertTrue(is_iterable([1, 2]))
        self.assertTrue(is_iterable(range(2)))


if __name__ == '__main__':
    unittest.main()
