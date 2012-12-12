import csv
import datetime
import os
from struct import pack
import sys

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest

from fitparse import FitFile
from fitparse.records import BASE_TYPES
from fitparse.utils import calc_crc


def generate_messages(mesg_num, local_mesg_num, field_defs, endian='<', data=None, flatten=True):
    mesgs = []
    base_type_list = []

    # definition message, local message num
    s = pack('<B', 0x40 | local_mesg_num)
    # reserved byte and endian
    s += pack('<xB', int(endian == '>'))
    # global message num, num fields
    s += pack('%sHB' % endian, mesg_num, len(field_defs))
    for def_num, base_type in field_defs:
        base_type = [bt for bt in BASE_TYPES.values() if bt.name == base_type][0]
        base_type_list.append(base_type)
        s += pack('<3B', def_num, base_type.size, base_type.identifier)

    mesgs.append(s)

    if data:
        for mesg_data in data:
            s = pack('B', local_mesg_num)
            for value, base_type in zip(mesg_data, base_type_list):
                s += pack("%s%s" % (endian, base_type.fmt), value)
            mesgs.append(s)

    return ''.join(mesgs) if flatten else mesgs


def generate_fitfile(data=None, endian='<'):
    fit_data = (
        generate_messages(
            # local mesg 0, global mesg 0 (file_id)
            mesg_num=0, local_mesg_num=0, endian=endian, field_defs=[
                # serial number, time_created, manufacturer
                (3, 'uint32z'), (4, 'uint32'), (1, 'uint16'),
                # product/garmin_product, number, type
                (2, 'uint16'), (5, 'uint16'), (0, 'enum'),
            ],
            # random serial number, random time, garmin, edge500, null, activity
            data=[[558069241, 723842606, 1, 1036, (2 ** 16) - 1, 4]],
        )
    )

    if data:
        fit_data += data

    # Prototcol version 1.0, profile version 1.52
    header = pack('<2BHI4s', 14, 16, 152, len(fit_data), '.FIT')
    file_data = header + pack('<H', calc_crc(header)) + fit_data
    return file_data + pack('<H', calc_crc(file_data))


def secs_to_dt(secs):
    return datetime.datetime.utcfromtimestamp(secs + 631065600)


def testfile(filename):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), 'files', filename)


class FitFileTestCase(unittest.TestCase):
    def test_basic_file_with_one_record(self, endian='<'):
        f = FitFile(generate_fitfile(endian=endian))
        f.parse()

        self.assertEqual(f.profile_version, 1.52)
        self.assertEqual(f.protocol_version, 1.0)

        file_id = f.messages[0]
        self.assertEqual(file_id.name, 'file_id')

        for field in ('type', 0):
            self.assertEqual(file_id.get_value(field), 'activity')
            self.assertEqual(file_id.get(field).raw_value, 4)
        for field in ('manufacturer', 1):
            self.assertEqual(file_id.get_value(field), 'garmin')
            self.assertEqual(file_id.get(field).raw_value, 1)
        for field in ('product', 'garmin_product', 2):
            self.assertEqual(file_id.get_value(field), 'edge500')
            self.assertEqual(file_id.get(field).raw_value, 1036)
        for field in ('serial_number', 3):
            self.assertEqual(file_id.get_value(field), 558069241)
        for field in ('time_created', 4):
            self.assertEqual(file_id.get_value(field), secs_to_dt(723842606))
            self.assertEqual(file_id.get(field).raw_value, 723842606)
        for field in ('number', 5):
            self.assertEqual(file_id.get_value(field), None)

    def test_basic_file_big_endian(self):
        self.test_basic_file_with_one_record('>')

    def test_component_field_accumulaters(self):
        # TODO: abstract CSV parsing
        csv_file = csv.reader(open(testfile('compressed-speed-distance-records.csv'), 'rb'))
        csv_file.next()  # Consume header

        f = FitFile(testfile('compressed-speed-distance.fit'))
        f.parse()

        records = f.get_messages(name='record')
        empty_record = records.next()  # Skip empty record for now (sets timestamp via header)

        # File's timestamp record is < 0x10000000, so field returns seconds
        self.assertEqual(empty_record.get_value('timestamp'), 17217864)

        # TODO: update using local_timestamp as offset, since we have this value as 2012 date

        for count, (record, (timestamp, heartrate, speed, distance, cadence)) in enumerate(zip(records, csv_file)):
            # No fancy datetime stuff, since timestamp record is < 0x10000000
            fit_ts = record.get_value('timestamp')
            self.assertIsInstance(fit_ts, int)
            self.assertLess(fit_ts, 0x10000000)
            self.assertEqual(fit_ts, int(timestamp))

            self.assertEqual(record.get_value('heart_rate'), int(heartrate))
            self.assertEqual(record.get_value('cadence'), int(cadence) if cadence != 'null' else None)
            self.assertAlmostEqual(record.get_value('speed'), float(speed))
            self.assertAlmostEqual(record.get_value('distance'), float(distance))

        self.assertEqual(count, 753)  # TODO: confirm size(records) = size(csv)

    def test_component_field_resolves_subfield(self):
        fit_data = generate_fitfile(
            generate_messages(
                # event (21), local message 1
                mesg_num=21, local_mesg_num=1, field_defs=[
                    # event, event_type, data16
                    (0, 'enum'), (1, 'enum'), (2, 'uint16'),
                ],
                data=[[0, 0, 2]],
            )
        )

        f = FitFile(fit_data)
        f.parse()

        event = f.messages[1]
        self.assertEqual(event.name, 'event')
        # Should be able to reference by original field name,
        # component field name, subfield name, and then the field def_num of both
        # the original field and component field
        for field in ('timer_trigger', 'data', 3):
            self.assertEqual(event.get_value(field), 'fitness_equipment')
            self.assertEqual(event.get(field).raw_value, 2)

        # Component field should be left as is
        for field in ('data16', 2):
            self.assertEqual(event.get_value(field), 2)

    def test_parsing_edge_500_fit_file(self):
        csv_messages = csv.reader(open(testfile('garmin-edge-500-activitiy-records.csv'), 'rb'))
        field_names = csv_messages.next()  # Consume header

        f = FitFile(testfile('garmin-edge-500-activitiy.fit'))
        messages = f.get_messages(name='record')

        # For fixups
        last_valid_lat, last_valid_long = None, None

        for message, csv_message in zip(messages, csv_messages):
            for csv_index, field_name in enumerate(field_names):
                fit_value, csv_value = message.get_value(field_name), csv_message[csv_index]
                if field_name == 'timestamp':
                    # Adjust GMT to PDT and format
                    fit_value = (fit_value - datetime.timedelta(hours=7)).strftime("%a %b %d %H:%M:%S PDT %Y")

                # Track last valid lat/longs
                if field_name == 'position_lat':
                    if fit_value is not None:
                        last_valid_lat = fit_value
                if field_name == 'position_long':
                    if fit_value is not None:
                        last_valid_long = fit_value

                # ANT FIT SDK Dump tool does a bad job of logging invalids, so fix them
                if fit_value is None:
                    # ANT FIT SDK Dump tool cadence reports invalid as 0
                    if field_name == 'cadence' and csv_value == '0':
                        csv_value = None
                    # ANT FIT SDK Dump tool invalid lat/lng reports as last valid
                    if field_name == 'position_lat':
                        fit_value = last_valid_lat
                    if field_name == 'position_long':
                        fit_value = last_valid_long

                if isinstance(fit_value, (int, long)):
                    csv_value = int(csv_value)

                if isinstance(fit_value, float):
                    # Float comparison
                    self.assertAlmostEqual(fit_value, float(csv_value))
                else:
                    self.assertEqual(fit_value, csv_value)

        try:
            messages.next()
            self.fail(".FIT file had more than csv file")
        except StopIteration:
            pass

        try:
            csv_messages.next()
            self.fail(".CSV file had more messages than .FIT file")
        except StopIteration:
            pass


if __name__ == '__main__':
    unittest.main()
