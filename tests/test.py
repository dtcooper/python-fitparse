#!/usr/bin/env python
#
# Copyright (c) 2011, David Cooper <dave@kupesoft.com>
# All rights reserved.
#
# Dedicated to Kate Lacey
#
# Permission to use, copy, modify, and/or distribute this software
# for any purpose with or without fee is hereby granted, provided
# that the above copyright notice, the above dedication, and this
# permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHORS DISCLAIMS ALL
# WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL
# THE AUTHORS BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

import os
import sys
import unittest

PROJECT_PATH = os.path.realpath(os.path.join(sys.path[0], '..'))
sys.path.append(PROJECT_PATH)

from fitparse.base import FitFile


def test_filename(filename):
    return os.path.join(
        os.path.dirname(os.path.realpath(__file__)),
        'data',
        filename,
    )


class FitFileTestCase(unittest.TestCase):
    def test_fitfile_parses_with_correct_number_of_recs_defs_and_file_size_and_CRC(self):
        fit = FitFile(test_filename('sample-activity.fit'))
        fit.parse()

        self.assertEquals(len(fit.records), 3228)
        self.assertEquals(len(fit.definitions), 9)
        self.assertEquals(fit.file_size, 104761)
        self.assertEquals(fit.crc, 0x75C5)


if __name__ == '__main__':
    unittest.main()
