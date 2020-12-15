import io
import os
import struct
import warnings

# Python 2 compat
try:
    num_types = (int, float, long)
except NameError:
    num_types = (int, float)

from fitparse.processors import FitFileDataProcessor
from fitparse.profile import FIELD_TYPE_TIMESTAMP, MESSAGE_TYPES
from fitparse.records import (
    Crc, DataMessage, FieldData, FieldDefinition, DevFieldDefinition, DefinitionMessage, MessageHeader,
    BASE_TYPES, BASE_TYPE_BYTE,
    add_dev_data_id, add_dev_field_description, get_dev_type
)
from fitparse.utils import fileish_open, is_iterable, FitParseError, FitEOFError, FitCRCError, FitHeaderError


class FitFile(object):
    def __init__(self, fileish, check_crc=True, data_processor=None):
        self._file = fileish_open(fileish, 'rb')

        self.check_crc = check_crc
        self._crc = None
        self._processor = data_processor or FitFileDataProcessor()

        # Get total filesize
        self._file.seek(0, os.SEEK_END)
        self._filesize = self._file.tell()
        self._file.seek(0, os.SEEK_SET)
        self._messages = []

        # Start off by parsing the file header (sets initial attribute values)
        self._parse_file_header()

    def __del__(self):
        self.close()

    def close(self):
        if hasattr(self, "_file") and self._file and hasattr(self._file, "close"):
            self._file.close()
            self._file = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    ##########
    # Private low-level utility methods for reading of fit file

    def _read(self, size):
        if size <= 0:
            return None
        data = self._file.read(size)
        if size != len(data):
            raise FitEOFError("Tried to read %d bytes from .FIT file but got %d" % (size, len(data)))

        if self.check_crc:
            self._crc.update(data)
        self._bytes_left -= len(data)
        return data

    def _read_struct(self, fmt, endian='<', data=None, always_tuple=False):
        fmt_with_endian = endian + fmt
        size = struct.calcsize(fmt_with_endian)
        if size <= 0:
            raise FitParseError("Invalid struct format: %s" % fmt_with_endian)

        if data is None:
            data = self._read(size)

        unpacked = struct.unpack(fmt_with_endian, data)
        # Flatten tuple if it's got only one value
        return unpacked if (len(unpacked) > 1) or always_tuple else unpacked[0]

    def _read_and_assert_crc(self, allow_zero=False):
        # CRC Calculation is little endian from SDK
        crc_computed, crc_read = self._crc.value, self._read_struct(Crc.FMT)
        if not self.check_crc:
            return
        if crc_computed == crc_read or (allow_zero and crc_read == 0):
            return
        raise FitCRCError('CRC Mismatch [computed: %s, read: %s]' % (
            Crc.format(crc_computed), Crc.format(crc_read)))

    ##########
    # Private Data Parsing Methods

    def _parse_file_header(self):

        # Initialize data
        self._accumulators = {}
        self._bytes_left = -1
        self._complete = False
        self._compressed_ts_accumulator = 0
        self._crc = Crc()
        self._local_mesgs = {}

        header_data = self._read(12)
        if header_data[8:12] != b'.FIT':
            raise FitHeaderError("Invalid .FIT File Header")

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
                raise FitHeaderError('Irregular File Header Size')

            # Consume extra two bytes of header and check CRC
            self._read_and_assert_crc(allow_zero=True)

            # Consume any extra bytes, since header size "may be increased in
            # "future to add additional optional information" (from SDK)
            self._read(extra_header_size - 2)

        # After we've consumed the header, set the bytes left to be read
        self._bytes_left = data_size

    def _parse_message(self):
        # When done, calculate the CRC and return None
        if self._bytes_left <= 0:
            if not self._complete:
                self._read_and_assert_crc()

            if self._file.tell() >= self._filesize:
                self._complete = True
                self.close()
                return None

            # Still have data left in the file - assuming chained fit files
            self._parse_file_header()
            return self._parse_message()

        header = self._parse_message_header()

        if header.is_definition:
            message = self._parse_definition_message(header)
        else:
            message = self._parse_data_message(header)
            if message.mesg_type is not None:
                if message.mesg_type.name == 'developer_data_id':
                    add_dev_data_id(message)
                elif message.mesg_type.name == 'field_description':
                    add_dev_field_description(message)

        self._messages.append(message)
        return message

    def _parse_message_header(self):
        header = self._read_struct('B')

        if header & 0x80:  # bit 7: Is this record a compressed timestamp?
            return MessageHeader(
                is_definition=False,
                is_developer_data=False,
                local_mesg_num=(header >> 5) & 0x3,  # bits 5-6
                time_offset=header & 0x1F,  # bits 0-4
            )
        else:
            return MessageHeader(
                is_definition=bool(header & 0x40),  # bit 6
                is_developer_data=bool(header & 0x20), # bit 5
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
                warnings.warn("Message %d: Invalid field size %d for field '%s' of type '%s' (expected a multiple of %d); falling back to byte encoding." % (
                    len(self._messages)+1, field_size, field.name, base_type.name, base_type.size))
                base_type = BASE_TYPE_BYTE

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

        dev_field_defs = []
        if header.is_developer_data:
            num_dev_fields = self._read_struct('B', endian=endian)
            for n in range(num_dev_fields):
                field_def_num, field_size, dev_data_index = self._read_struct('3B', endian=endian)
                field = get_dev_type(dev_data_index, field_def_num)
                dev_field_defs.append(DevFieldDefinition(
                    field=field,
                    dev_data_index=dev_data_index,
                    def_num=field_def_num,
                    size=field_size
                  ))

        def_mesg = DefinitionMessage(
            header=header,
            endian=endian,
            mesg_type=mesg_type,
            mesg_num=global_mesg_num,
            field_defs=field_defs,
            dev_field_defs=dev_field_defs,
        )
        self._local_mesgs[header.local_mesg_num] = def_mesg
        return def_mesg

    def _parse_raw_values_from_data_message(self, def_mesg):
        # Go through mesg's field defs and read them
        raw_values = []
        for field_def in def_mesg.field_defs + def_mesg.dev_field_defs:
            base_type = field_def.base_type
            is_byte = base_type.name == 'byte'
            # Struct to read n base types (field def size / base type size)
            struct_fmt = str(int(field_def.size / base_type.size)) + base_type.fmt

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

    def _apply_scale_offset(self, field, raw_value):
        # Apply numeric transformations (scale+offset)
        if isinstance(raw_value, tuple):
            # Contains multiple values, apply transformations to all of them
            return tuple(self._apply_scale_offset(field, x) for x in raw_value)
        elif isinstance(raw_value, num_types):
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

        # TODO: Maybe refactor this and make it simpler (or at least broken
        #       up into sub-functions)
        for field_def, raw_value in zip(def_mesg.field_defs + def_mesg.dev_field_defs, raw_values):
            field, parent_field = field_def.field, None
            if field:
                field, parent_field = self._resolve_subfield(field, def_mesg, raw_values)

                # Resolve component fields
                if field.components:
                    for component in field.components:
                        # Render its raw value
                        try:
                            cmp_raw_value = component.render(raw_value)
                        except ValueError:
                            continue

                        # Apply accumulated value
                        if component.accumulate and cmp_raw_value is not None:
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

                # TODO: Do we care about a base_type and a resolved field mismatch?
                # My hunch is we don't
                value = self._apply_scale_offset(field, field.render(raw_value))
            else:
                value = raw_value

            # Update compressed timestamp field
            if (field_def.def_num == FIELD_TYPE_TIMESTAMP.def_num) and (raw_value is not None):
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
                    field=FIELD_TYPE_TIMESTAMP,
                    parent_field=None,
                    value=FIELD_TYPE_TIMESTAMP.render(ts_value),
                    raw_value=ts_value,
                )
            )

        # Apply data processors
        for field_data in field_datas:
            # Apply type name processor
            self._processor.run_type_processor(field_data)
            self._processor.run_field_processor(field_data)
            self._processor.run_unit_processor(field_data)

        data_message = DataMessage(header=header, def_mesg=def_mesg, fields=field_datas)
        self._processor.run_message_processor(data_message)

        return data_message

    ##########
    # Public API

    def get_messages(self, name=None, with_definitions=False, as_dict=False):
        if with_definitions:  # with_definitions implies as_dict=False
            as_dict = False

        if name is not None:
            if is_iterable(name):
                names = set(name)
            else:
                names = set((name,))

        def should_yield(message):
            if with_definitions or message.type == 'data':
                # name arg is None we return all
                if name is None:
                    return True
                else:
                    if (message.name in names) or (message.mesg_num in names):
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
