#!/usr/bin/env python
import datetime
import sys

from fitparse import FitFileDataProcessor
from fitparse.profile import FIELD_TYPE_TIMESTAMP
from fitparse.records import FieldData

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest


class ProcessorsTestCase(unittest.TestCase):

    def test_fitfiledataprocessor(self):
        raw_value = 3600 + 60 + 1
        fd = FieldData(
            field_def=None,
            field=FIELD_TYPE_TIMESTAMP,
            parent_field=None,
            value=raw_value,
            raw_value=raw_value,
        )
        pr = FitFileDataProcessor()
        # local_date_time
        pr.process_type_local_date_time(fd)
        self.assertEqual(datetime.datetime(1989, 12, 31, 1, 1, 1), fd.value)
        pr.unparse_type_local_date_time(fd)
        self.assertEqual(raw_value, fd.raw_value)
        # localtime_into_day
        fd.value = raw_value
        fd.raw_value = None
        pr.process_type_localtime_into_day(fd)
        self.assertEqual(datetime.time(1, 1, 1), fd.value)
        pr.unparse_type_localtime_into_day(fd)
        self.assertEqual(raw_value, fd.raw_value)


if __name__ == '__main__':
    unittest.main()
