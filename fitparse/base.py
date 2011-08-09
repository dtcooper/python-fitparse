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
import struct

from fitparse import FitError, FitParseError, FitParseComplete
from fitparse import records as r


class FitFile(object):
    FILE_HEADER_FMT = '2BHI4s'
    RECORD_HEADER_FMT = 'B'

    # First two bytes of a definition, to get endian_ness
    DEFINITION_PART1_FMT = '2B'
    # Second part, relies on endianness and tells us how large the rest is
    DEFINITION_PART2_FMT = 'HB'
    # Field definitions
    DEFINITION_PART3_FIELDDEF_FMT = '3B'

    CRC_TABLE = (
        0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
    )

    def __init__(self, f):
        '''Create a fit file. Argument f can be an open file object or a filename'''
        if isinstance(f, str):
            f = open(f, 'rb')

        # Private: call FitFile.read(), don't read from this. Important for CRC.
        self._file = f
        self.file_size = os.path.getsize(f.name)
        self.data_read = 0
        self.crc = 0

        self.global_messages = {}
        self.definitions = []
        self.records = []

    def get_records_by_type(self, t):
        if isinstance(t, str):
            return (r for r in self.records if r.type.name == t)
        elif isinstance(t, int):
            return (r for r in self.records if r.type.num == t)
        elif isinstance(t, r.MessageType):
            return (r for r in self.records if r.type == t)
        else:
            raise FitError

    def parse(self, hook_function=None):
        # TODO: Document hook function
        self.parse_file_header()

        try:
            while True:
                record = self.parse_record()
                if hook_function:
                    hook_function(record)
        except FitParseComplete:
            pass

        # Compare CRC (read last two bytes on _file without recalculating CRC)
        stored_crc, = struct.unpack('H', self._file.read(2))

        if stored_crc != self.crc:
            raise FitParseError("Invalid CRC")

    def parse_record_header(self):
        header_data, = self.struct_read(FitFile.RECORD_HEADER_FMT)

        header_type = self.get_bit(header_data, 7)

        if header_type == r.RECORD_HEADER_NORMAL:
            message_type = self.get_bit(header_data, 6)
            local_message_type = header_data & 0b1111  # Bits 0-3
            # TODO: Should we set time_offset to 0?
            return r.RecordHeader(
                header_type, message_type, local_message_type, 0,
            )
        else:
            # Compressed timestamp
            local_message_type = (header_data >> 5) & 0b11  # bits 5-6
            seconds_offset = header_data & 0b1111  # bits 0-3
            return r.RecordHeader(
                header_type, r.MESSAGE_DATA, local_message_type, seconds_offset)

    def parse_definition_record(self, header):
        reserved, arch = self.struct_read(FitFile.DEFINITION_PART1_FMT)

        # We have the architecture now
        global_message_num, num_fields = self.struct_read(FitFile.DEFINITION_PART2_FMT, arch)

        # Fetch MessageType (unknown if it doesn't exist)
        message_type = r.MessageType(global_message_num)
        fields = []

        for field_num in range(num_fields):
            f_def_num, f_size, f_base_type_num = \
                               self.struct_read(FitFile.DEFINITION_PART3_FIELDDEF_FMT, arch)

            f_base_type_num = f_base_type_num & 0b11111  # bits 0-4

            try:
                field = message_type.fields[f_def_num]
            except (KeyError, TypeError):
                # Field type wasn't stored in message_type, fall back to a basic type
                field = r.Field('unknown', r.FieldTypeBase(f_base_type_num), None, None, None)

            fields.append(r.AllocatedField(field, f_size))

        definition = r.DefinitionRecord(header, message_type, arch, fields)
        self.global_messages[header.local_message_type] = definition

        self.definitions.append(definition)

        return definition  # Do we need to return?

    def parse_data_record(self, header):
        # XXX -- handle compressed timestamp header
        definition = self.global_messages[header.local_message_type]

        fields = []
        dynamic_fields = {}

        for i, (field, f_size) in enumerate(definition.fields):
            f_data, = self.struct_read(field.type.get_struct_fmt(f_size), definition.arch)
            # BoundField handles data conversion (if necessary)
            bound_field = r.BoundField(f_data, field)
            fields.append(bound_field)

            if isinstance(field, r.DynamicField):
                dynamic_fields[i] = bound_field

        # XXX -- This could probably be refactored heavily. It's slow and a bit unclear.
        # Go through already bound fields that are dynamic fields
        for dynamic_field_index, bound_field in dynamic_fields.iteritems():
            # Go by the reference field name and possible values
            for ref_field_name, possible_values in bound_field.field.possibilities.iteritems():
                # Go through the definitions fields looking for the reference field
                for field_index, (field, f_size) in enumerate(definition.fields):
                    # Did we find the refence field in the definition?
                    if field.name == ref_field_name:
                        # Get the reference field's value
                        ref_field_value = fields[field_index].data
                        # Is the reference field's value a value for a new dynamic field type?
                        new_field = possible_values.get(ref_field_value)
                        if new_field:
                            # Set it to the new type with old bound field's raw data
                            fields[dynamic_field_index] = r.BoundField(bound_field.raw_data, new_field)

        data = r.DataRecord(header, definition, fields)

        self.records.append(data)

        return data   # Do we need to return?

    def parse_record(self):
        record_header = self.parse_record_header()

        if record_header.message_type == r.MESSAGE_DEFINITION:
            return self.parse_definition_record(record_header)
        else:
            return self.parse_data_record(record_header)

    @staticmethod
    def get_bit(byte, bit_no):
        return (byte >> bit_no) & 1

    def read(self, size):
        '''Call read from the file, otherwise the CRC won't match.'''

        if self.data_read >= self.file_size - 2:
            raise FitParseComplete

        data = self._file.read(size)
        self.data_read += size

        for byte in data:
            self.calc_crc(ord(byte))

        return data

    def struct_read(self, fmt, endian=r.LITTLE_ENDIAN):
        endian = '<' if endian == r.LITTLE_ENDIAN else '>'
        fmt = '%s%s' % (endian, fmt)
        data = self.read(struct.calcsize(fmt))
        return struct.unpack(fmt, data)

    def calc_crc(self, char):
        # Taken almost verbatim from FITDTP section 3.3.2
        crc = self.crc
        tmp = FitFile.CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ FitFile.CRC_TABLE[char & 0xF]

        tmp = FitFile.CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        self.crc = crc ^ tmp ^ FitFile.CRC_TABLE[(char >> 4) & 0xF]

    def parse_file_header(self):
        '''Parse a fit file's header. This needs to be the first operation
        performed when opening a file'''
        def throw_exception(error):
            raise FitParseError("Bad .FIT file header: %s" % error)

        if self.file_size < 12:
            throw_exception("Invalid file size")

        # Parse the FIT header
        header_size, self.protocol_version, self.profile_version, data_size, data_type = \
                   self.struct_read(FitFile.FILE_HEADER_FMT)

        if header_size != 12:
            throw_exception("Invalid header size")

        if data_type != '.FIT':
            throw_exception('Data type not ".FIT"')

        # 12 byte header + 2 byte CRC = 14 bytes not included in that
        if self.file_size != 14 + data_size:
            throw_exception("File size not set correctly in header.")
