import os
import struct

from fitparse.exceptions import FitParseError, FitParseComplete
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
        '''
        Create a fit file. Argument f can be an open file-like object or a filename
        '''
        if isinstance(f, basestring):
            f = open(f, 'rb')

        # Private: call FitFile._read(), don't read from this. Important for CRC.
        self._file = f
        self._file_size = os.path.getsize(f.name)
        self._data_read = 0
        self._crc = 0

        self._last_timestamp = None
        self._global_messages = {}
        self.definitions = []
        self.records = []

    def get_records_by_type(self, t):
        # TODO: let t be a list/tuple of arbitary types (str, num, actual type)
        if isinstance(t, str):
            return (rec for rec in self.records if rec.type.name == t)
        elif isinstance(t, int):
            return (rec for rec in self.records if rec.type.num == t)
        elif isinstance(t, rec.MessageType):
            return (rec for rec in self.records if rec.type == t)
        else:
            return ()

    def get_records_as_dicts(self, t=None, with_ommited_fields=False):
        if t is None:
            records = self.records
        else:
            records = self.get_records_by_type(t)
        return (rec for rec in (rec.as_dict(with_ommited_fields) for rec in records) if rec)

    def parse(self, hook_func=None, hook_definitions=False):
        # TODO: Document hook function
        self._parse_file_header()

        try:
            while True:
                record = self._parse_record()
                if hook_func:
                    if hook_definitions or isinstance(record, r.DataRecord):
                        hook_func(record)
        except FitParseComplete:
            pass
        except Exception, e:
            self._file.close()
            raise FitParseError("Unexpected exception while parsing (%s: %s)" % (
                e.__class__.__name__, e,
            ))

        # Compare CRC (read last two bytes on _file without recalculating CRC)
        stored_crc, = struct.unpack('H', self._file.read(2))

        self._file.close()

        if stored_crc != self._crc:
            raise FitParseError("Invalid CRC")

    def _parse_record_header(self):
        header_data, = self._struct_read(FitFile.RECORD_HEADER_FMT)

        header_type = self._get_bit(header_data, 7)

        if header_type == r.RECORD_HEADER_NORMAL:
            message_type = self._get_bit(header_data, 6)
            local_message_type = header_data & 0b11111  # Bits 0-4
            # TODO: Should we set time_offset to 0?
            return r.RecordHeader(
                header_type, message_type, local_message_type, None,
            )
        else:
            # Compressed timestamp
            local_message_type = (header_data >> 5) & 0b11  # bits 5-6
            seconds_offset = header_data & 0b1111  # bits 0-3
            return r.RecordHeader(
                header_type, r.MESSAGE_DATA, local_message_type, seconds_offset)

    def _parse_definition_record(self, header):
        reserved, arch = self._struct_read(FitFile.DEFINITION_PART1_FMT)

        # We have the architecture now
        global_message_num, num_fields = self._struct_read(FitFile.DEFINITION_PART2_FMT, arch)

        # Fetch MessageType (unknown if it doesn't exist)
        message_type = r.MessageType(global_message_num)
        fields = []

        for field_num in range(num_fields):
            f_def_num, f_size, f_base_type_num = \
                               self._struct_read(FitFile.DEFINITION_PART3_FIELDDEF_FMT, arch)

            f_base_type_num = f_base_type_num & 0b11111  # bits 0-4

            try:
                field = message_type.fields[f_def_num]
            except (KeyError, TypeError):
                # unknown message has msg.fields as None = TypeError
                # if a known message doesn't define such a field = KeyError

                # Field type wasn't stored in message_type, fall back to a basic, unknown type
                field = r.Field(r.UNKNOWN_FIELD_NAME, r.FieldTypeBase(f_base_type_num), None, None, None)

            # XXX: -- very yucky!
            #  Convert extremely odd types where field size != type size to a byte
            #  field. They'll need to be handled customly. The FIT SDK has no examples
            #  of this but Cycling.fit on my Garmin Edge 500 does it, so I'll
            #  support it. This is probably the wrong way to do this, since it's
            #  not endian aware. Eventually, it should be a tuple/list of the type.
            #  Doing this will have to rethink the whole is_variable_size on FieldTypeBase
            calculated_f_size = struct.calcsize(
                self._get_endian_aware_struct(field.type.get_struct_fmt(f_size), arch)
            )
            if calculated_f_size != f_size:
                field = field._replace(type=r.FieldTypeBase(13))  # 13 = byte

            fields.append(r.AllocatedField(field, f_size))

        definition = r.DefinitionRecord(header, message_type, arch, fields)
        self._global_messages[header.local_message_type] = definition

        self.definitions.append(definition)

        return definition  # Do we need to return?

    def _parse_data_record(self, header):
        definition = self._global_messages[header.local_message_type]

        fields = []
        dynamic_fields = {}

        for i, (field, f_size) in enumerate(definition.fields):
            f_raw_data, = self._struct_read(field.type.get_struct_fmt(f_size), definition.arch)
            # BoundField handles data conversion (if necessary)
            bound_field = r.BoundField(f_raw_data, field)

            if field.name == r.COMPRESSED_TIMESTAMP_FIELD_NAME and \
               field.type.name == r.COMPRESSED_TIMESTAMP_TYPE_NAME:
                self._last_timestamp = f_raw_data

            fields.append(bound_field)

            if isinstance(field, r.DynamicField):
                dynamic_fields[i] = bound_field

        # XXX -- This could probably be refactored heavily. It's slow and a bit unclear.
        # Go through already bound fields that are dynamic fields
        if dynamic_fields:
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
                                break

        if header.type == r.RECORD_HEADER_COMPRESSED_TS:
            ts_field = definition.type.fields.get(r.TIMESTAMP_FIELD_DEF_NUM)
            if ts_field:
                timestamp = self._last_timestamp + header.seconds_offset
                fields.append(r.BoundField(timestamp, ts_field))
                self._last_timestamp = timestamp

        # XXX -- do compressed speed distance decoding here, similar to compressed ts
        # ie, inject the fields iff they're in definition.type.fields

        data = r.DataRecord(header, definition, fields)

        self.records.append(data)

        return data   # Do we need to return?

    def _parse_record(self):
        record_header = self._parse_record_header()

        if record_header.message_type == r.MESSAGE_DEFINITION:
            return self._parse_definition_record(record_header)
        else:
            return self._parse_data_record(record_header)

    @staticmethod
    def _get_bit(byte, bit_no):
        return (byte >> bit_no) & 1

    def _read(self, size):
        '''Call read from the file, otherwise the CRC won't match.'''

        if self._data_read >= self._file_size - 2:
            raise FitParseComplete

        data = self._file.read(size)
        self._data_read += size

        for byte in data:
            self._calc_crc(ord(byte))

        return data

    @staticmethod
    def _get_endian_aware_struct(fmt, endian):
        endian = '<' if endian == r.LITTLE_ENDIAN else '>'
        return '%s%s' % (endian, fmt)

    def _struct_read(self, fmt, endian=r.LITTLE_ENDIAN):
        fmt = self._get_endian_aware_struct(fmt, endian)
        data = self._read(struct.calcsize(fmt))
        return struct.unpack(fmt, data)

    def _calc_crc(self, char):
        # Taken almost verbatim from FITDTP section 3.3.2
        crc = self._crc
        tmp = FitFile.CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ FitFile.CRC_TABLE[char & 0xF]

        tmp = FitFile.CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        self._crc = crc ^ tmp ^ FitFile.CRC_TABLE[(char >> 4) & 0xF]

    def _parse_file_header(self):
        '''Parse a fit file's header. This needs to be the first operation
        performed when opening a file'''
        def throw_exception(error):
            raise FitParseError("Bad .FIT file header: %s" % error)

        if self._file_size < 12:
            throw_exception("Invalid file size")

        # Parse the FIT header
        header_size, self.protocol_version, self.profile_version, data_size, data_type = \
                   self._struct_read(FitFile.FILE_HEADER_FMT)
        num_extra_bytes = 0

        if header_size < 12:
            throw_exception("Invalid header size")
        elif header_size > 12:
            # Read and discard some extra bytes in the header
            # as per https://github.com/dtcooper/python-fitparse/issues/1
            num_extra_bytes = header_size - 12
            self._read(num_extra_bytes)

        if data_type != '.FIT':
            throw_exception('Data type not ".FIT"')

        # 12 byte header + 2 byte CRC = 14 bytes not included in that
        if self._file_size != 14 + data_size + num_extra_bytes:
            throw_exception("File size not set correctly in header.")
