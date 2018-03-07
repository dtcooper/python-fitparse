import os
import re
import struct

import six

from fitparse import FitFileDataProcessor, profile, utils
from .records import Crc, DataMessage, DefinitionMessage, MessageHeader, FieldData, FieldDefinition
from .utils import fileish_open, FitParseError


class FitFileEncoder(object):
    def __init__(self, fileish,
                 protocol_version=1.0, profile_version=20.33,
                 data_processor=None):
        """
        Create FIT encoder.

        :param fileish: file-ish object,
        :param protocol_version: protocol version, change to 2.0 if you use developer fields.
        :param profile_version: profile version.
        :param data_processor: custom data processor.
        """
        self.protocol_version = float(protocol_version)
        self.profile_version = float(profile_version)

        self._processor = data_processor or FitFileDataProcessor()
        self._file = fileish_open(fileish, 'wb')
        self._byte_start = 0
        self._bytes_written = 0
        self._compressed_ts_accumulator = 0
        self._local_mesgs = {}
        self.data_size = 0
        self.completed = False
        self._crc = Crc()

        self._write_file_header_place()

    def __del__(self):
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.finish()
        if hasattr(self, "_file") and self._file and hasattr(self._file, "close"):
            self._file.close()
            self._file = None

    ##########
    # Private low-level utility methods for writing of fit file

    def _write(self, data):
        if not data:
            return
        self._file.write(data)
        self._bytes_written += len(data)
        self._crc.update(data)

    def _write_struct(self, data, fmt, endian='<'):
        fmt_with_endian = endian + fmt
        size = struct.calcsize(fmt_with_endian)
        if size <= 0:
            raise FitParseError('Invalid struct format: {}'.format(fmt_with_endian))
        # handle non iterable and iterable data
        if utils.is_iterable(data):
            packed = struct.pack(fmt_with_endian, *data)
        else:
            packed = struct.pack(fmt_with_endian, data)
        self._write(packed)
        return packed

    @staticmethod
    def _check_number_bits(n, bits, errmsg):
        if n & ~ bits != 0:
            raise FitParseError('{}: too large: {}'.format(errmsg, n))

    ##########
    # Private data unparsing methods
    @staticmethod
    def _is_ts_field(field):
        return field and field.def_num == profile.FIELD_TYPE_TIMESTAMP.def_num

    def _write_file_header_place(self):
        """Write zeroes instead of header."""
        self._byte_start = self._file.tell()
        self._write(b'\0' * 14)
        self._bytes_written = 0

    def _write_file_header(self):
        # encode versions
        protocol_major, protocol_minor = re.match(r'([\d]+)\.(\d+)', str(self.protocol_version)).groups()
        protocol_ver_enc = (int(protocol_major) << 4) | int(protocol_minor)
        profile_ver_enc = int(round(self.profile_version * 100))
        self.data_size = self._bytes_written

        self._file.seek(self._byte_start, os.SEEK_SET)
        data = self._write_struct((14, protocol_ver_enc, profile_ver_enc, self.data_size, b'.FIT'), '2BHI4s')
        crc = Crc(byte_arr=data)
        self._write_struct(crc.value, Crc.FMT)
        self._file.seek(0, os.SEEK_END)

    def _write_message_header(self, header):
        data = 0
        if header.time_offset is not None:  # compressed timestamp
            self._check_number_bits(header.local_mesg_num, 0x3, 'Message header local_mesg_num')
            self._check_number_bits(header.time_offset, 0x1f, 'Message header time_offset')
            data = 0x80  # bit 7
            data |= header.local_mesg_num << 5  # bits 5-6
            data |= header.time_offset  # bits 0-4
        else:
            self._check_number_bits(header.local_mesg_num, 0xf, 'Message header local_mesg_num')
            if header.is_definition:
                data |= 0x40  # bit 6
            if header.is_developer_data:
                data |= 0x20  # bit 5
            data |= header.local_mesg_num  # bits 0 - 3
        self._write_struct(data, 'B')

    def _write_definition_message(self, def_mesg):
        if not self._local_mesgs and def_mesg.name != 'file_id':
            raise FitParseError('First message must be file_id')

        self._write_message_header(def_mesg.header)
        # reserved and architecture bytes
        endian = def_mesg.endian
        data = int(endian == '>')
        self._write_struct(data, 'xB')
        # rest of header with endian awareness
        data = (def_mesg.mesg_num, len(def_mesg.field_defs))
        self._write_struct(data, 'HB', endian=endian)
        for field_def in def_mesg.field_defs:
            data = (field_def.def_num, field_def.size, field_def.base_type.identifier)
            self._write_struct(data, '3B', endian=endian)
        if def_mesg.header.is_developer_data:
            data = len(def_mesg.dev_field_defs)
            self._write_struct(data, 'B', endian=endian)
            for field_def in def_mesg.dev_field_defs:
                data = (field_def.def_num, field_def.size, field_def.dev_data_index)
                self._write_struct(data, '3B', endian=endian)
        self._local_mesgs[def_mesg.header.local_mesg_num] = def_mesg

    @staticmethod
    def _unapply_compressed_accumulation(raw_value, accumulation, num_bits, errmsg):
        max_value = (1 << num_bits) - 1
        max_mask = max_value - 1

        diff = raw_value - accumulation
        if diff < 0 or diff > max_value:
            raise FitParseError('{}: too large: {}'.format(errmsg, raw_value))

        return raw_value & max_mask

    def _prepare_compressed_ts(self, mesg):
        """Apply timestamp to header."""
        field_datas = [f for f in mesg.fields if self._is_ts_field(f)]
        if len(field_datas) > 1:
            raise FitParseError('Too many timestamp fields. Do not mix raw timestamp and header timestamp.')
        if len(field_datas) <= 0:
            return
        field_data = field_datas[0]
        raw_value = field_data.raw_value
        if raw_value is None:
            return
        if not field_data.field_def:
            # header timestamp
            mesg.header.time_offset = self._unapply_compressed_accumulation(raw_value,
                                                                            self._compressed_ts_accumulator,
                                                                            5,
                                                                            'Message header time_offset')
        # raw and header timestamp field
        self._compressed_ts_accumulator = raw_value

    def _write_raw_values_from_data_message(self, mesg):
        field_datas = mesg.fields
        def_mesg = mesg.def_mesg
        for field_def in def_mesg.all_field_defs():
            base_type = field_def.base_type
            is_byte = base_type.name == 'byte'
            field_data = next((f for f in field_datas if f.field_def == field_def), None)
            raw_value = field_data.raw_value if field_data else None

            # If the field returns with a tuple of values it's definitely an
            # oddball, but we'll parse it on a per-value basis it.
            # If it's a byte type, treat the tuple as a single value
            if not is_byte and isinstance(raw_value, tuple):
                raw_value = tuple(base_type.in_range(base_type.unparse(rv)) for rv in raw_value)
            else:
                # Otherwise, just scrub the singular value
                raw_value = base_type.in_range(base_type.unparse(raw_value))
            size = field_def.size
            if not size:
                raise FitParseError('FieldDefinition has no size: {}'.format(field_def.name))

            # Struct to write n base types (field def size / base type size)
            struct_fmt = '%d%s' % (
                size / base_type.size,
                base_type.fmt,
            )
            try:
                self._write_struct(raw_value, struct_fmt, endian=def_mesg.endian)
            except struct.error as ex:
                six.raise_from(FitParseError('struct.error: Wrong value or fmt for: {}, fmt: {}, value: {}'.format(field_def.name, struct_fmt, raw_value)), ex)

    def _write_data_message(self, mesg):
        """Compute raw_value and size."""
        self._processor.unparse_message(mesg)
        for field_data in mesg.fields:
            # clear possible mess from DataMessageCreator reuse
            field_data.raw_value = None
            # Apply processor
            self._processor.unparse_type(field_data)
            self._processor.unparse_field(field_data)
            self._processor.unparse_unit(field_data)

            field = field_data.field
            # Sometimes raw_value is set by processor, otherwise take value.
            # It's a design flaw od the library data structures.
            raw_value = field_data.raw_value
            if raw_value is None:
                raw_value = field_data.value

            if field:
                raw_value = field.unrender(raw_value)
                raw_value = field.unapply_scale_offset(raw_value)
            field_data.raw_value = raw_value

        self._prepare_compressed_ts(mesg)
        self._write_message_header(mesg.header)
        self._write_raw_values_from_data_message(mesg)

    def finish(self):
        """Write header and CRC."""
        if self.completed:
            return
        crc = self._crc.value
        self._write_file_header()
        self._write_struct(crc, Crc.FMT)
        self.completed = True

    def write(self, mesg):
        """
        Write message.

        :param mesg: message to write
        :type mesg: Union[DefinitionMessage,DataMessage]
        """
        if isinstance(mesg, DataMessageCreator):
            mesg = mesg.mesg
        elif mesg.type == 'definition':
            self._write_definition_message(mesg)
            return

        def_mesg = mesg.def_mesg
        if not def_mesg:
            raise ValueError('mesg does not have def_mesg')
        old_def_mesg = self._local_mesgs.get(mesg.header.local_mesg_num)
        if old_def_mesg != def_mesg:
            self._write_definition_message(def_mesg)
        self._write_data_message(mesg)


class DataMessageCreator(object):

    def __init__(self, type_name, local_mesg_num=0, endian='<'):
        """
        DataMessage creator to simplify message creatiron for the Encoder.
        Use freeze() if you want to resue the DefinitionMessage and set values again.

        :param Union[str,int] type_name: message type name or number, see profile.MESSAGE_TYPES
        :param int local_mesg_num: local message number
        :param str endian: character '<' or '>'
        """
        self.endian = endian
        self.frozen = False
        self.def_mesg = self._create_definition_message(type_name, local_mesg_num=local_mesg_num)
        self.mesg = self._create_data_message(self.def_mesg)

    def set_value(self, name, value, size=None):
        """
        Set value of given field.

        :param str name: field name
        :param value: field value
        :param int or None size: size of value, None for autoguess
        :rtype None:
        """
        field_data = self._get_or_create_field_data(name)
        field_data.value = value
        base_type = field_data.base_type
        if size is None:
            if base_type.name == 'byte':
                size = len(value) if value is not None else 1
            elif base_type.name == 'string':
                size = len(value) + 1  # 0x00 in the end
            elif utils.is_iterable(value):
                size = len(value)
            else:
                size = 1
        size *= base_type.size
        field_def = field_data.field_def
        if not self.frozen:
            field_def.size = size
        else:
            if field_def.size != size:
                raise ValueError('Frozen: cannot change field size: {}'.format(name))

    def set_values(self, values):
        """Set values.
         :param Iterable[str, Any] values: iterable values in tuples (name, value). Better to use iterables with predictable order of items."""
        if values is None:
            return
        for name, value in values:
            self.set_value(name, value)

    def set_header_timestamp(self, value):
        """Set value for the compressed header timestamp (time_offset).

        :param Union[datetime.datetime,int] value: date time or number of sec (see FIT doc)
        """
        field_data = self.mesg.get(profile.FIELD_TYPE_TIMESTAMP.name)
        if field_data and field_data.field_def:
            raise ValueError('Raw timestamp already set. Do not mix raw timestamp and header timestamp.')
        if not field_data:
            field_data = FieldData(
                field_def=None,
                field=profile.FIELD_TYPE_TIMESTAMP,
                parent_field=None,
                units='s'
            )
            self.mesg.fields.append(field_data)
        field_data.value = value

    def freeze(self):
        """Freeze fields, so as the DefinitionMessage cannot change."""
        self.frozen = True

    def _create_definition_message(self, type_name, local_mesg_num=0):
        """Create skeleton of new definition message.
        :param Union[str,int] type_name: message type name or number, see profile.MESSAGE_TYPES
        :param local_mesg_num: local message number.
        :rtype DefinitionMessage
        """
        if not type_name:
            raise ValueError('no type_name')
        mesg_type = profile.MESSAGE_TYPES.get(type_name)
        if not mesg_type:
            mesg_type = next((m for m in profile.MESSAGE_TYPES.values() if m.name == type_name), None)
        if not mesg_type:
            raise FitParseError('Message type not found: {}'.format(type_name))
        header = MessageHeader(
            is_definition=True,
            is_developer_data=False,
            local_mesg_num=local_mesg_num
        )

        return DefinitionMessage(
            header=header,
            endian=self.endian,
            mesg_type=mesg_type,
            mesg_num=mesg_type.mesg_num,
            field_defs=[],
            dev_field_defs=[]
        )

    def _create_data_message(self, def_msg):
        """
        Create empty data message.

        :rtype DataMessage"""
        if not def_msg:
            raise ValueError('No def_msg.')

        header = MessageHeader(
            is_definition=False,
            is_developer_data=def_msg.header.is_developer_data,
            local_mesg_num=def_msg.header.local_mesg_num
        )
        msg = DataMessage(
            header=header,
            def_mesg=def_msg,
            fields=[]
        )
        return msg

    def _get_or_create_field_data(self, name):
        """

        :param str name: field name
        :rtype FieldData:
        """
        field_data = self.mesg.get(name)
        if field_data:
            return field_data
        if self.frozen:
            raise ValueError('Frozen: cannot create FieldData: {}'.format(name))
        field_def, subfield = self._get_or_create_field_definition(name)
        field = field_def.field
        parent_field = None
        if subfield:
            parent_field = field
            field = subfield

        field_data = FieldData(
            field_def=field_def,
            field=field,
            parent_field=parent_field,
            units=None
        )
        self.mesg.fields.append(field_data)
        return field_data

    def _get_or_create_field_definition(self, name):
        """

        :param str name:
        :rtype tuple(FieldDefinition, SubField):
        """
        field_def = self.def_mesg.get_field_def(name)
        if field_def:
            raise field_def
        field, subfield = self.def_mesg.mesg_type.get_field_and_subfield(name)
        if not field:
            raise ValueError(
                'No field: {} in the message: {} (#{})'.format(name, self.def_mesg.name, self.def_mesg.mesg_num))
        field_def = FieldDefinition(
            field=field,
            def_num=field.def_num,
            base_type=field.base_type
        )
        self.def_mesg.field_defs.append(field_def)
        return (field_def, subfield)
