#!/usr/bin/env python
import copy
import datetime
import io
import os
import sys

from fitparse import FitFile
from fitparse.encoder import FitFileEncoder, DataMessageCreator

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest


def testfile(filename):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'files', filename)


class FitFileEncoderTestCase(unittest.TestCase):

    def test_header(self):
        file = io.BytesIO()
        with FitFileEncoder(file) as fwrite:
            fwrite.finish()
            buff = file.getvalue()
            pass
        self.assertTrue(fwrite.completed)
        self.assertEqual(16, len(buff))

        with FitFile(buff) as fread:
            self.assertEqual(0, len(fread.messages))
            self.assertEqual(fwrite.protocol_version, fread.protocol_version)
            self.assertEqual(fwrite.profile_version, fread.profile_version)
            self.assertEqual(fwrite.data_size, fread.data_size)

    def test_basic_activity_create(self):
        file = io.BytesIO()
        # copy of written messages
        messages = []
        time_created = datetime.datetime(2017, 12, 13, 14, 15, 16)
        with FitFileEncoder(file) as fwrite:
            def write(mesg):
                fwrite.write(mesg)
                messages.append(copy.deepcopy(mesg.mesg))

            mesg = DataMessageCreator('file_id')
            mesg.set_values((
                ('serial_number', 123456),
                ('manufacturer', 'dynastream'),
                ('garmin_product', 'hrm1'),  # test subfield
                ('type', 'activity'),
                ('time_created', time_created)
            ))
            write(mesg)

            mesg = DataMessageCreator('device_info')
            mesg.set_values((
                ('manufacturer', 284),
                ('product', 1),
                ('product_name', 'unit test')  # test string
            ))
            write(mesg)

            rec_mesg = DataMessageCreator('record', local_mesg_num=1)
            rec_mesg.set_values((
                ('timestamp', time_created),
                ('altitude', 100),
                ('distance', 0)
            ))
            write(rec_mesg)

            rec_mesg2 = DataMessageCreator('record', local_mesg_num=2)
            rec_mesg2.set_values((
                ('altitude', 102),
                ('distance', 2)
            ))
            rec_mesg2.set_header_timestamp(time_created + datetime.timedelta(seconds=2))
            write(rec_mesg2)

            rec_mesg2.set_values((
                ('altitude', 40000),  # out of sint16 range
                ('distance', 4)
            ))
            rec_mesg2.set_header_timestamp(time_created + datetime.timedelta(seconds=4))
            write(rec_mesg2)
            messages[-1].get('altitude').value = None  # to conform the assert

            mesg = DataMessageCreator('session')
            mesg.set_values((
                ('start_time', time_created),
                ('timestamp', time_created),
                ('total_distance', 20.5),
                ('total_ascent', 1234),
                ('total_descent', 654),
                ('total_elapsed_time', 3661.5),
                ('avg_altitude', 821),
                ('sport', 'cycling'),
                ('event', 'session'),
                ('event_type', 'start')
            ))
            write(mesg)

            fwrite.finish()
            buff = file.getvalue()

        with FitFile(buff) as fread:
            rmessages = fread.messages

        self._assert_messages(messages, rmessages)

    def test_basic_activity_read_write(self):
        # note: 'Activity.fit' has some useless definition messages
        with FitFile(testfile('Activity.fit')) as fread:
            messages = fread.messages

        file = io.BytesIO()
        with FitFileEncoder(file) as fwrite:
            for m in messages:
                # current encoder can do just basic fields
                m.fields = [f for f in m.fields if f.field_def or FitFileEncoder._is_ts_field(f)]
                # need to unset raw_value
                for field_data in m.fields:
                    field_data.raw_value = None
                fwrite.write(m)
            fwrite.finish()
            buff = file.getvalue()

        with FitFile(buff) as fread:
            messages_buff = fread.messages

        self._assert_messages(messages, messages_buff)

    def _assert_messages(self, expected, actual):
        self.assertEqual(len(expected), len(actual), msg='#messages')
        for emsg, amsg in zip(expected, actual):
            self.assertEqual(emsg.name, amsg.name)
            self._assert_message_headers(emsg.header, amsg.header)
            self.assertEqual(self._get_header_ts(emsg.fields), self._get_header_ts(amsg.fields), msg='message: {} header timestamp'.format(emsg.name))
            efields = self._filter_fields_for_test(emsg.fields)
            afields = self._filter_fields_for_test(amsg.fields)
            self.assertEqual(len(efields), len(afields), msg='message: {} #fields'.format(emsg.name))
            for efield, afield in zip(efields, afields):
                self.assertEqual(efield.name, afield.name, msg='message: {} field names'.format(emsg.name))
                self.assertEqual(efield.value, afield.value,
                                 msg='message: {}, field: {} values'.format(emsg.name, efield.name))

    def _assert_message_headers(self, expected, actual):
        self.assertEqual(expected.is_definition, actual.is_definition)
        self.assertEqual(expected.is_developer_data, actual.is_developer_data)
        self.assertEqual(expected.local_mesg_num, actual.local_mesg_num)
        self.assertEqual(expected.time_offset, actual.time_offset)

    @staticmethod
    def _filter_fields_for_test(fields):
        """Take only base field for the test."""
        return [f for f in fields if f.field_def]

    @staticmethod
    def _get_header_ts(fields):
        """Get timestamp related to the compressed header."""
        field_data = next((f for f in fields if f.field_def is None and FitFileEncoder._is_ts_field(f)), None)
        return field_data.value if field_data else None


if __name__ == '__main__':
    unittest.main()
