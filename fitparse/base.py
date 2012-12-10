import struct

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

from fitparse.profile import MESSAGE_TYPES
from fitparse.records import (
    DataMessage, FieldData, FieldDefinition, DefinitionMessage, MessageHeader,
    BASE_TYPES, BASE_TYPE_BYTE
)
from fitparse.utils import calc_crc


# TODO: put in button of profile.py
def get_timestamp_field():
    for mesg_type in MESSAGE_TYPES.values():
        field = mesg_type.fields.get(TIMESTAMP_DEF_NUM)
        if field:
            return field
    raise Exception("TODO: no date_time")

TIMESTAMP_DEF_NUM = 253
DATE_TIME_FIELD = get_timestamp_field()


class FitParseError(Exception):
    pass


class FitFile(object):
    def __init__(self, fileish, check_crc=True):
        if isinstance(fileish, basestring):
            try:
                self._file = open(fileish, 'rb')
            except:
                # If the header smells a string containing a fit file, we'll
                # wrap it with StringIO
                if fileish[8:12] != '.FIT':
                    raise
                self._file = StringIO.StringIO(fileish)
        else:
            self._file = fileish

        self.check_crc = check_crc

        self._crc = 0
        self._data_bytes_left = -1  # Not valid until after _parse_file_header()
        self._local_mesgs = {}
        self._accumulators = {}
        self._compressed_ts_accumulator = 0
        self._complete = False
        self._messages = []

        # Start off by parsing the file header (makes self._data_bytes_left valid)
        self._parse_file_header()

    ##########
    # Private low-level utility methods for reading of fit file

    def _read(self, size):
        if size <= 0:
            return ''
        data = self._file.read(size)
        self._crc = calc_crc(data, self._crc)
        self._data_bytes_left -= len(data)
        return data

    def _read_struct(self, fmt, endian='<', data=None, always_tuple=False):
        fmt_with_endian = "%s%s" % (endian, fmt)
        size = struct.calcsize(fmt)
        if data is None:
            data = self._read(size)

        if size != len(data):
            raise FitParseError("Tried to read %d bytes from .FIT file but got %d" % (size, len(data)))

        unpacked = struct.unpack(fmt_with_endian, data)
        # Flatten tuple if it's got only one value
        return unpacked if (len(unpacked) > 1) or always_tuple else unpacked[0]

    def _read_and_assert_crc(self, allow_zero=False):
        # CRC Calculation is little endian from SDK
        crc_expected, crc_actual = self._crc, self._read_struct('H')

        if (crc_actual != crc_expected) and not (allow_zero and (crc_actual == 0)):
            if self.check_crc:
                raise FitParseError('CRC Mismatch [expected = 0x%04X, actual = 0x%04X]' % (
                    crc_expected, crc_actual))

    ##########
    # Private Data Parsing Methods

    def _parse_file_header(self):
        header_data = self._read(12)
        if header_data[8:12] != '.FIT':
            raise FitParseError("Invalid .FIT File Header")

        # Larger fields are explicitly little endian from SDK
        header_size, protocol_ver_enc, profile_ver_enc, data_size = self._read_struct('2BHI4x', data=header_data)

        # Decode the same way the SDK does
        self.protocol_version = float("%d.%d" % (protocol_ver_enc >> 4, protocol_ver_enc & ((1 << 4) - 1)))
        self.profile_version = float("%d.%d" % (profile_ver_enc / 100, profile_ver_enc % 100))

        # Consume extra header information
        extra_header_size = header_size - 12
        if extra_header_size > 0:
            # Make sure extra field in header is at least 2 bytes to calculate CRC
            if extra_header_size < 2:
                raise FitParseError('Irregular File Header Size')

            # Consume extra two bytes of header and check CRC
            self._read_and_assert_crc(allow_zero=True)

            # Consume any extra bytes, since header size "may be increased in
            # "future to add additional optional information" (from SDK)
            self._read(extra_header_size - 2)

        # After we've consumed the header, set the bytes left to be read
        self._data_bytes_left = data_size

    def _parse_message(self):
        # When done, calculate the CRC and return None
        if self._data_bytes_left <= 0:
            if not self._complete:
                self._read_and_assert_crc()

                if hasattr(self._file, 'close'):
                    self._file.close()
                self._complete = True

            return None

        header = self._parse_message_header()

        if header.is_definition:
            message = self._parse_definition_message(header)
        else:
            message = self._parse_data_message(header)

        self._messages.append(message)
        return message

    def _parse_message_header(self):
        header = self._read_struct('B')

        if header & 0x80:  # bit 7: Is this record a compressed timestamp?
            return MessageHeader(
                is_definition=False,
                local_mesg_num=(header >> 5) & 0x3,  # bits 5-6
                time_offset=header & 0x1F,  # bits 0-4
            )
        else:
            return MessageHeader(
                is_definition=bool(header & 0x40),  # bit 6
                local_mesg_num=header & 0xF,  # bits 0-3
                time_offset=None,
            )

    def _parse_definition_message(self, header):
        # Read reserved byte and architecture byte to resolve endian
        endian = '>' if self._read_struct('xB') else '<'
        # Read rest of header with endian awareness
        global_mesg_num, num_fields = self._read_struct('HB', endian=endian)
        mesg_type = MESSAGE_TYPES.get(global_mesg_num)
        field_defs = []

        for n in range(num_fields):
            field_def_num, field_size, base_type_num = self._read_struct('3B', endian=endian)
            # Try to get field from message type (None if unknown)
            field = mesg_type.fields.get(field_def_num) if mesg_type else None
            base_type = BASE_TYPES.get(base_type_num, BASE_TYPE_BYTE)

            if (field_size % base_type.size) != 0:
                # NOTE: we could fall back to byte encoding if there's any
                # examples in the wild. For now, just throw an exception
                raise FitParseError("Invalid field size %d for type '%s' (expected a multiple of %d)" % (
                    field_size, base_type.name, base_type.size))

            # If the field has components that are accumulators
            # start recording their accumulation at 0
            if field and field.components:
                for component in field.components:
                    if component.accumulate:
                        accumulators = self._accumulators.setdefault(global_mesg_num, {})
                        accumulators[component.def_num] = 0

            field_defs.append(FieldDefinition(
                field=field,
                def_num=field_def_num,
                base_type=base_type,
                size=field_size,
            ))

        def_mesg = DefinitionMessage(
            header=header,
            endian=endian,
            mesg_type=mesg_type,
            mesg_num=global_mesg_num,
            field_defs=field_defs,
        )
        self._local_mesgs[header.local_mesg_num] = def_mesg
        return def_mesg

    def _parse_raw_values_from_data_message(self, def_mesg):
        # Go through mesg's field defs and read them
        raw_values = []
        for field_def in def_mesg.field_defs:
            base_type = field_def.base_type
            is_byte = base_type.name == 'byte'
            # Struct to read n base types (field def size / base type size)
            struct_fmt = '%d%s' % (
                field_def.size / base_type.size,
                base_type.fmt,
            )

            # Extract the raw value, ask for a tuple if it's a byte type
            raw_value = self._read_struct(
                struct_fmt, endian=def_mesg.endian, always_tuple=is_byte,
            )

            # If the field returns with a tuple of values it's definitely an
            # oddball, but we'll parse it on a per-value basis it.
            # If it's a byte type, treat the tuple as a single value
            if isinstance(raw_value, tuple) and not is_byte:
                raw_value = tuple(base_type.parse(rv) for rv in raw_value)
            else:
                # Otherwise, just scrub the singular value
                raw_value = base_type.parse(raw_value)

            raw_values.append(raw_value)
        return raw_values

    @staticmethod
    def _resolve_subfield(field, def_mesg, raw_values):
        # Resolve into (field, parent) ie (subfield, field) or (field, None)
        if field.subfields:
            for sub_field in field.subfields:
                # Go through reference fields for this sub field
                for ref_field in sub_field.ref_fields:
                    # Go through field defs AND their raw values
                    for field_def, raw_value in zip(def_mesg.field_defs, raw_values):
                        # If there's a definition number AND raw value match on the
                        # reference field, then we return this subfield
                        if (field_def.def_num == ref_field.def_num) and (ref_field.raw_value == raw_value):
                            return sub_field, field
        return field, None

    @staticmethod
    def _apply_scale_offset(field, raw_value):
        # Apply numeric transformations (scale+offset)
        if isinstance(raw_value, (int, long, float)):
            if field.scale:
                raw_value = float(raw_value) / field.scale
            if field.offset:
                raw_value = raw_value - field.offset
        return raw_value

    @staticmethod
    def _apply_compressed_accumulation(raw_value, accumulation, num_bits):
        max_value = (1 << num_bits)
        max_mask = max_value - 1
        base_value = raw_value + (accumulation & ~max_mask)

        if raw_value < (accumulation & max_mask):
            base_value += max_value

        return base_value

    def _parse_data_message(self, header):
        def_mesg = self._local_mesgs.get(header.local_mesg_num)
        if not def_mesg:
            raise FitParseError('Got data message with invalid local message type %d' % (
                header.local_mesg_num))

        raw_values = self._parse_raw_values_from_data_message(def_mesg)
        field_datas = []  # TODO: I don't love this name, update on DataMessage too

        for field_def, raw_value in zip(def_mesg.field_defs, raw_values):
            field, parent_field = field_def.field, None
            if field:
                if field.components:
                    for component in field.components:
                        # Render it's raw value
                        cmp_raw_value = component.render(raw_value)

                        if component.accumulate:
                            accumulator = self._accumulators[def_mesg.mesg_num]
                            cmp_raw_value = self._apply_compressed_accumulation(
                                cmp_raw_value, accumulator[component.def_num], component.bits,
                            )
                            accumulator[component.def_num] = cmp_raw_value

                        # Apply scale and offset from component, not from the dynamic field
                        # as they may differ
                        cmp_raw_value = self._apply_scale_offset(component, cmp_raw_value)

                        # Extract the component's dynamic field from def_mesg
                        cmp_field = def_mesg.mesg_type.fields[component.def_num]
                        # Resolve a possible subfield
                        cmp_field, cmp_parent_field = self._resolve_subfield(cmp_field, def_mesg, raw_values)
                        cmp_value = cmp_field.render(cmp_raw_value)

                        # Plop it on field_datas
                        field_datas.append(
                            FieldData(
                                field_def=None,
                                field=cmp_field,
                                parent_field=cmp_parent_field,
                                value=cmp_value,
                                raw_value=cmp_raw_value,
                            )
                        )

                else:
                    # Component fields shouldn't also have subfields
                    field, parent_field = self._resolve_subfield(field, def_mesg, raw_values)

                # TODO: Do we care about a base_type and a resolved field mismatch?
                # My hunch is we don't
                value = self._apply_scale_offset(field, field.render(raw_value))
            else:
                value = raw_value

            # Update compressed timestamp field
            if (field_def.def_num == TIMESTAMP_DEF_NUM) and (raw_value is not None):
                self._compressed_ts_accumulator = raw_value

            field_datas.append(
                FieldData(
                    field_def=field_def,
                    field=field,
                    parent_field=parent_field,
                    value=value,
                    raw_value=raw_value,
                )
            )

        # Apply timestamp field if we got a header
        if header.time_offset is not None:
            ts_value = self._compressed_ts_accumulator = self._apply_compressed_accumulation(
                header.time_offset, self._compressed_ts_accumulator, 5,
            )
            field_datas.append(
                FieldData(
                    field_def=None,
                    field=DATE_TIME_FIELD,
                    parent_field=None,
                    value=DATE_TIME_FIELD.render(ts_value),
                    raw_value=ts_value,
                )
            )

        return DataMessage(header=header, def_mesg=def_mesg, fields=field_datas)

    ##########
    # Public API

    def get_messages(
        self, name=None, mesg_num=None, has_field=None,
        with_definitions=False, as_dict=False,
    ):
        # TODO: Implement the query arguments, also let them be tuples, ie name=('record', 'event')

        if with_definitions:  # with_definitions implies as_dict=False
            as_dict = False

        def should_yield(message):
            if message and (with_definitions or message.type == 'data'):
                # If both args are None, then we return all
                if (name is None) and (mesg_num is None):
                    return True
                if (name is not None) and name in (message.name, message.mesg_num):
                    return True
                if (mesg_num is not None) and mesg_num == message.mesg_num:
                    return True
            return False

        # Yield all parsed messages first
        for message in self._messages:
            if should_yield(message):
                yield message.as_dict() if as_dict else message

        # If there are unparsed messages, yield those too
        while not self._complete:
            message = self._parse_message()
            if message and should_yield(message):
                yield message.as_dict() if as_dict else message

    @property
    def messages(self):
        # TODO: could this be more efficient?
        return list(self.get_messages())

    def parse(self):
        while self._parse_message():
            pass

    def __iter__(self):
        return self.get_messages()


# TODO: Create subclasses like Activity and do per-value monkey patching
# for example local_timestamp to adjust timestamp on a per-file basis
