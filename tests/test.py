#!/usr/bin/env python

import os
import sys
import unittest

PROJECT_PATH = os.path.realpath(os.path.join(sys.path[0], '..'))
sys.path.append(PROJECT_PATH)

from fitparse.base import FitFile


def testfile(*filename):
    return os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'data',
        os.path.join(*filename),
    )


class FitFileTestCase(unittest.TestCase):
    def test_fitfile_parses_with_correct_number_of_recs_defs_and_file_size_and_CRC(self):
        fit = FitFile(testfile('sample-activity.fit'))
        fit.parse()

        self.assertEquals(len(fit.records), 3228)
        self.assertEquals(len(fit.definitions), 9)
        self.assertEquals(fit._file_size, 104761)
        self.assertEquals(fit._crc, 0x75C5)


if __name__ == '__main__':
    unittest.main()
