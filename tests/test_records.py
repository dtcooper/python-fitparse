#!/usr/bin/env python

import sys

from fitparse.records import Crc

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest


class RecordsTestCase(unittest.TestCase):
    def test_crc(self):
        crc = Crc()
        self.assertEqual(0, crc.value)
        crc.update(b'\x0e\x10\x98\x00(\x00\x00\x00.FIT')
        self.assertEqual(0xace7, crc.value)
        # 0 must not change the crc
        crc.update(0)
        self.assertEqual(0xace7, crc.value)

    def test_crc_format(self):
        self.assertEqual('0x0000', Crc.format(0))
        self.assertEqual('0x12AB', Crc.format(0x12AB))


if __name__ == '__main__':
    unittest.main()
