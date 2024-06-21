#!/usr/bin/env python

import io
import os
import struct
import warnings

from fitparse.processors import FitFileDataProcessor
from fitparse.profile import FIELD_TYPE_TIMESTAMP, MESSAGE_TYPES
from fitparse.records import (
    Crc, DevField, DataMessage, FieldData, FieldDefinition, DevFieldDefinition, DefinitionMessage,
    MessageHeader, BASE_TYPES, BASE_TYPE_BYTE,
)
from fitparse.utils import fileish_open, is_iterable, FitParseError, FitEOFError, FitCRCError, FitHeaderError


class DeveloperDataMixin:
    def __init__(self, *args, check_developer_data=True, **kwargs):
        self.check_developer_data = check_developer_data
        self.dev_types = {}

        super().__init__(*args, **kwargs)

    def _append_dev_data_id(self, dev_data_index, application_id=None, fields=None):
        if fields is None:
            fields = {}

        # Note that nothing in the spec says overwriting an existing type is invalid
        self.dev_types[dev_data_index] = {
            'dev_data_index': dev_data_index,
            'application_id': application_id,
            'fields': fields
        }

    def add_dev_data_id(self, message):
        dev_data_index = message.get_raw_value('developer_data_index')
        application_id = message.get_raw_value('application_id')

        self._append_dev_data_id(dev_data_index, application_id)

    def _append_dev_field_description(self, dev_data_index, field_def_num, type=BASE_TYPE_BYTE, name=None,
                                      units=None, native_field_num=None):
        if dev_data_index not in self.dev_types:
            if self.check_developer_data:
                raise FitParseError("No such dev_data_index=%s found" % (dev_data_index))

            warnings.warn(
                "Dev type for dev_data_index=%s missing. Adding dummy dev type." % (dev_data_index)
            )
            self._append_dev_data_id(dev_data_index)

        self.dev_types[dev_data_index]["fields"][field_def_num] = DevField(
            dev_data_index=dev_data_index,
            def_num=field_def_num,
            type=type,
            name=name,
            units=units,
            native_field_num=native_field_num
        )

    def add_dev_field_description(self, message):
        dev_data_index = message.get_raw_value('developer_data_index')
        field_def_num = message.get_raw_value('field_definition_number')
        base_type_id = message.get_raw_value('fit_base_type_id')
        field_name = message.get_raw_value('field_name') or "unnamed_dev_field_%s" % field_def_num
        units = message.get_raw_value("units")
        native_field_num = message.get_raw_value('native_field_num')

        if dev_data_index not in self.dev_types:
            if self.check_developer_data:
                raise FitParseError("No such dev_data_index=%s found" % (dev_data_index))

            warnings.warn(
                "Dev type for dev_data_index=%s missing. Adding dummy dev type." % (dev_data_index)
            )
            self._append_dev_data_id(dev_data_index)

        fields = self.dev_types[int(dev_data_index)]['fields']

        # Note that nothing in the spec says overwriting an existing field is invalid
        fields[field_def_num] = DevField(
            dev_data_index=dev_data_index,
            def_num=field_def_num,
            type=BASE_TYPES[base_type_id],
            name=field_name,
            units=units,
            native_field_num=native_field_num
        )

    def get_dev_type(self, dev_data_index, field_def_num):
        if dev_data_index not in self.dev_types:
            if self.check_developer_data:
                raise FitParseError(
                    f"No such dev_data_index={dev_data_index} found when looking up field {field_def_num}"
                )

            warnings.warn(
                "Dev type for dev_data_index=%s missing. Adding dummy dev type." % (dev_data_index)
            )
            self._append_dev_data_id(dev_data_index)

        dev_type = self.dev_types[dev_data_index]

        if field_def_num not in dev_type['fields']:
            if self.check_developer_data:
                raise FitParseError(
                    f"No such field {field_def_num} for dev_data_index {dev_data_index}"
                )

            warnings.warn(
                f"Field {field_def_num} for dev_data_index {dev_data_index} missing. Adding dummy field."
            )
            self._append_dev_field_description(
                dev_data_index=dev_data_index,
                field_def_num=field_def_num
            )

        return dev_type['fields'][field_def_num]


class FitFileDecoder(DeveloperDataMixin):
    """Basic decoder for fit files"""

    def __init__(self, fileish, *args, check_crc=True, data_processor=None, **kwargs):
        self._file = fileish_open(fileish, 'rb')

        self.check_crc = check_crc
        self._crc = None

        # Get total filesize
        self._file.seek(0, os.SEEK_END)
        self._filesize = self._file.tell()
        self._file.seek(0, os.SEEK_SET)

        # Start off by parsing the file header (sets initial attribute values)
        self._parse_file_header()

        super().__init__(*args, **kwargs)

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
        # TODO - How to handle the case of unterminated file? Error out and have user retry with check_crc=false?
        crc_computed, crc_read = self._crc.value, self._read_struct(Crc.FMT)
        if not self.check_crc:
            return
        if crc_computed == crc_read or (allow_zero and crc_read == 0):
            return
        raise FitCRCError('CRC Mismatch [computed: {}, read: {}]'.format(
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
            # Don't assert CRC if requested not
            if not self._complete and self.check_crc:
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
                    self.add_dev_data_id(message)
                elif message.mesg_type.name == 'field_description':
                    self.add_dev_field_description(message)

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
                warnings.warn(
                    "Invalid field size %d for field '%s' of type '%s' (expected a multiple of %d); falling back to byte encoding." % (
                    field_size, field.name, base_type.name, base_type.size)
                )
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
                field = self.get_dev_type(dev_data_index, field_def_num)
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
            try:
                raw_value = self._read_struct(
                    struct_fmt, endian=def_mesg.endian, always_tuple=is_byte,
                )
            except FitEOFError:
                # file was suddenly terminated
                warnings.warn("File was terminated unexpectedly, some data will not be loaded.")
                break

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
        elif isinstance(raw_value, (int, float)):
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

    def _parse_data_message_components(self, header):
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

        return header, def_mesg, field_datas

    def _parse_data_message(self, header):
        header, def_mesg, field_datas = self._parse_data_message_components(header)
        return DataMessage(header=header, def_mesg=def_mesg, fields=field_datas)

    @staticmethod
    def _should_yield(message, with_definitions, names):
        if not message:
            return False
        if with_definitions or message.type == 'data':
            # name arg is None we return all
            if names is None:
                return True
            elif (message.name in names) or (message.mesg_num in names):
                return True
        return False

    @staticmethod
    def _make_set(obj):
        if obj is None:
            return None

        if is_iterable(obj):
            return set(obj)
        else:
            return {obj}

    ##########
    # Public API

    def get_messages(self, name=None, with_definitions=False, as_dict=False):
        if with_definitions:  # with_definitions implies as_dict=False
            as_dict = False

        names = self._make_set(name)

        while not self._complete:
            message = self._parse_message()
            if self._should_yield(message, with_definitions, names):
                yield message.as_dict() if as_dict else message

    def __iter__(self):
        return self.get_messages()


class CacheMixin:
    """Add message caching to the FitFileDecoder"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._messages = []

    def _parse_message(self):
        self._messages.append(super()._parse_message())
        return self._messages[-1]

    def get_messages(self, name=None, with_definitions=False, as_dict=False):
        if with_definitions:  # with_definitions implies as_dict=False
            as_dict = False

        names = self._make_set(name)

        # Yield all parsed messages first
        for message in self._messages:
            if self._should_yield(message, with_definitions, names):
                yield message.as_dict() if as_dict else message

        for message in super().get_messages(names, with_definitions, as_dict):
            yield message

    @property
    def messages(self):
        return list(self.get_messages())

    def parse(self):
        while self._parse_message():
            pass


class DataProcessorMixin:
    """Add data processing to the FitFileDecoder"""

    def __init__(self, *args, **kwargs):
        self._processor = kwargs.pop("data_processor", None) or FitFileDataProcessor()
        super().__init__(*args, **kwargs)

    def _parse_data_message(self, header):
        header, def_mesg, field_datas = self._parse_data_message_components(header)

        # Apply data processors
        for field_data in field_datas:
            # Apply type name processor
            self._processor.run_type_processor(field_data)
            self._processor.run_field_processor(field_data)
            self._processor.run_unit_processor(field_data)

        data_message = DataMessage(header=header, def_mesg=def_mesg, fields=field_datas)
        self._processor.run_message_processor(data_message)

        return data_message


class UncachedFitFile(DataProcessorMixin, FitFileDecoder):
    """FitFileDecoder with data processing"""

    def __init__(self, fileish, *args, check_crc=True, data_processor=None, **kwargs):
        # Ensure all optional params are passed as kwargs
        super().__init__(
            fileish,
            *args,
            check_crc=check_crc,
            data_processor=data_processor,
            **kwargs
        )


class FitFile(CacheMixin, UncachedFitFile):
    """FitFileDecoder with caching and data processing"""
    pass



# TODO: Create subclasses like Activity and do per-value monkey patching
# for example local_timestamp to adjust timestamp on a per-file basis
