#!/usr/bin/env python

import csv
import datetime
import os
from struct import pack
import sys
import warnings

from fitparse import FitFile
from fitparse.processors import UTC_REFERENCE, StandardUnitsDataProcessor
from fitparse.records import BASE_TYPES, Crc
from fitparse.utils import FitEOFError, FitCRCError, FitHeaderError

if sys.version_info >= (2, 7):
    import unittest
else:
    import unittest2 as unittest


def generate_messages(mesg_num, local_mesg_num, field_defs, endian='<', data=None):
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

    return b''.join(mesgs)


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
    header = pack('<2BHI4s', 14, 16, 152, len(fit_data), b'.FIT')
    file_data = header + pack('<' + Crc.FMT, Crc.calculate(header)) + fit_data
    return file_data + pack('<' + Crc.FMT, Crc.calculate(file_data))


def secs_to_dt(secs):
    return datetime.datetime.utcfromtimestamp(secs + UTC_REFERENCE)


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
        csv_fp = open(testfile('compressed-speed-distance-records.csv'), 'r')
        csv_file = csv.reader(csv_fp)
        next(csv_file)  # Consume header

        f = FitFile(testfile('compressed-speed-distance.fit'))
        f.parse()

        records = f.get_messages(name='record')
        empty_record = next(records)  # Skip empty record for now (sets timestamp via header)

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
        csv_fp.close()

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
        for field in ('event', 0):
            self.assertEqual(event.get_value(field), 'timer')
            self.assertEqual(event.get(field).raw_value, 0)
        for field in ('event_type', 1):
            self.assertEqual(event.get_value(field), 'start')
            self.assertEqual(event.get(field).raw_value, 0)

        # Should be able to reference by original field name,
        # component field name, subfield name, and then the field def_num of both
        # the original field and component field
        for field in ('timer_trigger', 'data', 3):
            self.assertEqual(event.get_value(field), 'fitness_equipment')
            self.assertEqual(event.get(field).raw_value, 2)

        # Component field should be left as is
        for field in ('data16', 2):
            self.assertEqual(event.get_value(field), 2)

    def test_subfield_components(self):
        # sore = 123, opponent_score = 456, total = 29884539
        sport_point_value = 123 + (456 << 16)
        # rear_gear_num = 4, rear_gear, = 20, front_gear_num = 2, front_gear = 34
        gear_chance_value = 4 + (20 << 8) + (2 << 16) + (34 << 24)

        fit_data = generate_fitfile(
            generate_messages(
                # event (21), local message 1
                mesg_num=21, local_mesg_num=1, field_defs=[
                    # event, data
                    (0, 'enum'), (3, 'uint32'),
                ],
                data=[
                    # sport point
                    [33, sport_point_value],
                    # front gear change
                    [42, gear_chance_value],
                ],
            )
        )

        f = FitFile(fit_data)
        f.parse()

        sport_point = f.messages[1]
        self.assertEqual(sport_point.name, 'event')
        for field in ('event', 0):
            self.assertEqual(sport_point.get_value(field), 'sport_point')
            self.assertEqual(sport_point.get(field).raw_value, 33)
        for field in ('sport_point', 'data', 3):
            # Verify raw numeric value
            self.assertEqual(sport_point.get_value(field), sport_point_value)
        for field in ('score', 7):
            self.assertEqual(sport_point.get_value(field), 123)
        for field in ('opponent_score', 8):
            self.assertEqual(sport_point.get_value(field), 456)

        gear_change = f.messages[2]
        self.assertEqual(gear_change.name, 'event')
        for field in ('event', 0):
            self.assertEqual(gear_change.get_value(field), 'front_gear_change')
            self.assertEqual(gear_change.get(field).raw_value, 42)
        for field in ('gear_change_data', 'data', 3):
            # Verify raw numeric value
            self.assertEqual(gear_change.get_value(field), gear_chance_value)
        for field in ('front_gear_num', 9):
            self.assertEqual(gear_change.get_value(field), 2)
        for field in ('front_gear', 10):
            self.assertEqual(gear_change.get_value(field), 34)
        for field in ('rear_gear_num', 11):
            self.assertEqual(gear_change.get_value(field), 4)
        for field in ('rear_gear', 12):
            self.assertEqual(gear_change.get_value(field), 20)

    def test_parsing_edge_500_fit_file(self):
        self._csv_test_helper(
            'garmin-edge-500-activity.fit',
            'garmin-edge-500-activity-records.csv')

    def test_parsing_fenix_5_bike_fit_file(self):
        self._csv_test_helper(
            'garmin-fenix-5-bike.fit',
            'garmin-fenix-5-bike-records.csv')

    def test_parsing_fenix_5_run_fit_file(self):
        self._csv_test_helper(
            'garmin-fenix-5-run.fit',
            'garmin-fenix-5-run-records.csv')

    def test_parsing_fenix_5_walk_fit_file(self):
        self._csv_test_helper(
            'garmin-fenix-5-walk.fit',
            'garmin-fenix-5-walk-records.csv')

    def test_parsing_edge_820_fit_file(self):
        self._csv_test_helper(
            'garmin-edge-820-bike.fit',
            'garmin-edge-820-bike-records.csv')

    def _csv_test_helper(self, fit_file, csv_file):
        csv_fp = open(testfile(csv_file), 'r')
        csv_messages = csv.reader(csv_fp)
        field_names = next(csv_messages)  # Consume header

        f = FitFile(testfile(fit_file))
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

                if isinstance(fit_value, int):
                    csv_value = int(fit_value)
                if csv_value == '':
                    csv_value = None

                if isinstance(fit_value, float):
                    # Float comparison
                    self.assertAlmostEqual(fit_value, float(csv_value))
                else:
                    self.assertEqual(fit_value, csv_value,
                        msg="For %s, FIT value '%s' did not match CSV value '%s'" % (field_name, fit_value, csv_value))

        try:
            next(messages)
            self.fail(".FIT file had more than csv file")
        except StopIteration:
            pass

        try:
            next(csv_messages)
            self.fail(".CSV file had more messages than .FIT file")
        except StopIteration:
            pass

        csv_fp.close()

    def test_developer_types(self):
        """Test that a file with developer types in it can be parsed"""
        FitFile(testfile('developer-types-sample.fit')).parse()
        FitFile(testfile('20170518-191602-1740899583.fit')).parse()
        FitFile(testfile('DeveloperData.fit')).parse()

    def test_invalid_crc(self):
        try:
            FitFile(testfile('activity-filecrc.fit')).parse()
            self.fail("Didn't detect an invalid CRC")
        except FitCRCError:
            pass

    def test_unexpected_eof(self):
        try:
            FitFile(testfile('activity-unexpected-eof.fit')).parse()
            self.fail("Didn't detect an unexpected EOF")
        except FitEOFError:
            pass

    def test_chained_file(self):
        FitFile(testfile('activity-settings.fit')).parse()

    def test_invalid_chained_files(self):
        """Detect errors when files are chained together

        Note that 'chained' means just concatinated in this case
        """
        try:
            FitFile(testfile('activity-activity-filecrc.fit')).parse()
            self.fail("Didn't detect a CRC error in the chained file")
        except FitCRCError:
            pass

        try:
            FitFile(testfile('activity-settings-corruptheader.fit')).parse()
            self.fail("Didn't detect a header error in the chained file")
        except FitHeaderError:
            pass

        try:
            FitFile(testfile('activity-settings-nodata.fit')).parse()
            self.fail("Didn't detect an EOF error in the chaned file")
        except FitEOFError:
            pass

    def test_valid_files(self):
        """Test that parsing a bunch of random known-good files works"""
        for x in ('2013-02-06-12-11-14.fit', '2015-10-13-08-43-15.fit',
                  'Activity.fit', 'Edge810-Vector-2013-08-16-15-35-10.fit',
                  'MonitoringFile.fit', 'Settings.fit', 'Settings2.fit',
                  'WeightScaleMultiUser.fit', 'WeightScaleSingleUser.fit',
                  'WorkoutCustomTargetValues.fit', 'WorkoutIndividualSteps.fit',
                  'WorkoutRepeatGreaterThanStep.fit', 'WorkoutRepeatSteps.fit',
                  'activity-large-fenxi2-multisport.fit', 'activity-small-fenix2-run.fit',
                  'antfs-dump.63.fit', 'sample-activity-indoor-trainer.fit',
                  'sample-activity.fit', 'garmin-fenix-5-bike.fit',
                  'garmin-fenix-5-run.fit', 'garmin-fenix-5-walk.fit',
                  'garmin-edge-820-bike.fit', 'null_compressed_speed_dist.fit'):
            FitFile(testfile(x)).parse()

    def test_units_processor(self):
        for x in ('2013-02-06-12-11-14.fit', '2015-10-13-08-43-15.fit',
                  'Activity.fit', 'Edge810-Vector-2013-08-16-15-35-10.fit',
                  'MonitoringFile.fit', 'Settings.fit', 'Settings2.fit',
                  'WeightScaleMultiUser.fit', 'WeightScaleSingleUser.fit',
                  'WorkoutCustomTargetValues.fit', 'WorkoutIndividualSteps.fit',
                  'WorkoutRepeatGreaterThanStep.fit', 'WorkoutRepeatSteps.fit',
                  'activity-large-fenxi2-multisport.fit', 'activity-small-fenix2-run.fit',
                  'antfs-dump.63.fit', 'sample-activity-indoor-trainer.fit',
                  'sample-activity.fit', 'garmin-fenix-5-bike.fit',
                  'garmin-fenix-5-run.fit', 'garmin-fenix-5-walk.fit',
                  'garmin-edge-820-bike.fit'):
            FitFile(testfile(x), data_processor=StandardUnitsDataProcessor()).parse()

    def test_int_long(self):
        """Test that ints are properly shifted and scaled"""
        with FitFile(testfile('event_timestamp.fit')) as f:
            assert f.messages[-1].fields[1].raw_value == 863.486328125

    def test_elemnt_bolt_developer_data_id_without_application_id(self):
        """Test that a file without application id set inside developer_data_id is parsed
        (as seen on ELEMNT BOLT with firmware version WB09-1507)"""
        FitFile(testfile('elemnt-bolt-no-application-id-inside-developer-data-id.fit')).parse()

    def test_multiple_header(self):
        f = FitFile(testfile('sample_mulitple_header.fit'))
        assert len(f.messages) == 3023

    def test_speed(self):
        f = FitFile(testfile('2019-02-17-062644-ELEMNT-297E-195-0.fit'))
        avg_speed = list(f.get_messages('session'))[0].get_values().get('avg_speed')
        self.assertEqual(avg_speed, 5.86)

    def test_mismatched_field_size(self):
        f = FitFile(testfile('coros-pace-2-cycling-misaligned-fields.fit'))
        with warnings.catch_warnings(record=True) as w:
            f.parse()
            assert len(w) == 5
            assert all("falling back to byte encoding" in str(x) for x in w)
        self.assertEqual(len(f.messages), 11293)

    # TODO:
    #  * Test Processors:
    #    - process_type_<>, process_field_<>, process_units_<>, process_message_<>


if __name__ == '__main__':
    unittest.main()
