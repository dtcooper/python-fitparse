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

import csv
import os
import sys
import unittest

PROJECT_PATH = os.path.realpath(os.path.join(sys.path[0], '..'))
sys.path.append(PROJECT_PATH)

from fitparse.base import FitFile
from fitparse.records import MESSAGE_DEFINITION, MESSAGE_DATA


header_message_types = {
    'Data': MESSAGE_DATA,
    'Definition': MESSAGE_DEFINITION,
}


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
        self.assertEquals(fit.file_size, 104761)
        self.assertEquals(fit.crc, 0x75C5)


class FitSDKExamplesTestCase(unittest.TestCase):
    test_data_dir = 'FIT-SDK-1.2-examples'


def create_fit_sdk_example_test(file_prefix):
    def test_fit_sdk_example(self):
        fitfile_name = testfile(self.test_data_dir, "%s.fit" % file_prefix)
        csvfile_name = testfile(self.test_data_dir, "%s.csv" % file_prefix)

        c = csv.reader(open(csvfile_name, 'rb'))
        c.next()  # Skip the first row

        fit = FitFile(fitfile_name)

        def hook_function(record):
            row = c.next()
            message_type, local_message_num, message_name = row[:3]

            # TODO -- need to do way more checking here
            self.assertEqual(message_name, record.type.name)
            self.assertEqual(header_message_types[message_type], record.header.message_type)

        fit.parse(hook_function)

    test_fit_sdk_example.__name__ = 'test_fit_sdk_example_%s' % file_prefix
    return test_fit_sdk_example

for f in os.listdir(testfile(FitSDKExamplesTestCase.test_data_dir)):
    if f.lower().endswith('.fit'):
        test_method = create_fit_sdk_example_test(f[:-4])
        setattr(FitSDKExamplesTestCase, test_method.__name__, test_method)


if __name__ == '__main__':
    unittest.main()
