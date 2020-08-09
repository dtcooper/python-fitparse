import math
import struct

# Python 2 compat
try:
    int_types = (int, long,)
    byte_iter = bytearray
except NameError:
    int_types = (int,)
    byte_iter = lambda x: x

try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest

from fitparse.utils import FitParseError


DEV_TYPES = {}


class RecordBase(object):
    # namedtuple-like base class. Subclasses should must __slots__
    __slots__ = ()

    # TODO: switch back to namedtuple, and don't use default arguments as None
    #       and see if that gives us any performance improvements

    def __init__(self, *args, **kwargs):
        for slot_name, value in zip_longest(self.__slots__, args, fillvalue=None):
            setattr(self, slot_name, value)
        for slot_name, value in kwargs.items():
            setattr(self, slot_name, value)


class MessageHeader(RecordBase):
    __slots__ = ('is_definition', 'is_developer_data', 'local_mesg_num', 'time_offset')

    def __repr__(self):
        return '<MessageHeader: %s%s -- local mesg: #%d%s>' % (
            'definition' if self.is_definition else 'data',
            '(developer)' if self.is_developer_data else '',
            self.local_mesg_num,
            ', time offset: %d' % self.time_offset if self.time_offset else '',
        )


class DefinitionMessage(RecordBase):
    __slots__ = ('header', 'endian', 'mesg_type', 'mesg_num', 'field_defs', 'dev_field_defs')
    type = 'definition'

    @property
    def name(self):
        return self.mesg_type.name if self.mesg_type else 'unknown_%d' % self.mesg_num

    def __repr__(self):
        return '<DefinitionMessage: %s (#%d) -- local mesg: #%d, field defs: [%s], dev field defs: [%s]>' % (
            self.name,
            self.mesg_num,
            self.header.local_mesg_num,
            ', '.join([fd.name for fd in self.field_defs]),
            ', '.join([fd.name for fd in self.dev_field_defs]),
        )


class FieldDefinition(RecordBase):
    __slots__ = ('field', 'def_num', 'base_type', 'size')

    @property
    def name(self):
        return self.field.name if self.field else 'unknown_%d' % self.def_num

    @property
    def type(self):
        return self.field.type if self.field else self.base_type

    def __repr__(self):
        return '<FieldDefinition: %s (#%d) -- type: %s (%s), size: %d byte%s>' % (
            self.name,
            self.def_num,
            self.type.name, self.base_type.name,
            self.size, 's' if self.size != 1 else '',
        )


class DevFieldDefinition(RecordBase):
    __slots__ = ('field', 'dev_data_index', 'base_type', 'def_num', 'size')

    def __init__(self, **kwargs):
        super(DevFieldDefinition, self).__init__(**kwargs)
        # For dev fields, the base_type and type are always the same.
        self.base_type = self.type

    @property
    def name(self):
        return self.field.name if self.field else 'unknown_dev_%d_%d' % (self.dev_data_index, self.def_num)

    @property
    def type(self):
        return self.field.type

    def __repr__(self):
        return '<DevFieldDefinition: %s:%s (#%d) -- type: %s, size: %d byte%s>' % (
            self.name,
            self.dev_data_index,
            self.def_num,
            self.type.name,
            self.size, 's' if self.size != 1 else '',
        )


class DataMessage(RecordBase):
    __slots__ = ('header', 'def_mesg', 'fields')
    type = 'data'

    def get(self, field_name, as_dict=False):
        # SIMPLIFY: get rid of as_dict
        for field_data in self.fields:
            if field_data.is_named(field_name):
                return field_data.as_dict() if as_dict else field_data

    def get_raw_value(self, field_name):
        field_data = self.get(field_name)
        if field_data:
            return field_data.raw_value
        return None

    def get_value(self, field_name):
        # SIMPLIFY: get rid of this completely
        field_data = self.get(field_name)
        if field_data:
            return field_data.value

    def get_values(self):
        # SIMPLIFY: get rid of this completely
        return dict((f.name if f.name else f.def_num, f.value) for f in self.fields)

    @property
    def name(self):
        return self.def_mesg.name

    @property
    def mesg_num(self):
        # SIMPLIFY: get rid of this
        return self.def_mesg.mesg_num

    @property
    def mesg_type(self):
        # SIMPLIFY: get rid of this
        return self.def_mesg.mesg_type

    def as_dict(self):
        # TODO: rethink this format
        return {
            'name': self.name,
            'fields': [f.as_dict() for f in self.fields],
        }

    def __iter__(self):
        # Sort by whether this is a known field, then its name
        return iter(sorted(self.fields, key=lambda fd: (int(fd.field is None), fd.name)))

    def __repr__(self):
        return '<DataMessage: %s (#%d) -- local mesg: #%d, fields: [%s]>' % (
            self.name, self.mesg_num, self.header.local_mesg_num,
            ', '.join(["%s: %s" % (fd.name, fd.value) for fd in self.fields]),
        )

    def __str__(self):
        # SIMPLIFY: get rid of this
        return '%s (#%d)' % (self.name, self.mesg_num)


class FieldData(RecordBase):
    __slots__ = ('field_def', 'field', 'parent_field', 'value', 'raw_value', 'units')

    def __init__(self, *args, **kwargs):
        super(FieldData, self).__init__(self, *args, **kwargs)
        if not self.units and self.field:
            # Default to units on field, otherwise None.
            # NOTE:Not a property since you may want to override this in a data processor
            self.units = self.field.units

    @property
    def name(self):
        return self.field.name if self.field else 'unknown_%d' % self.def_num

    # TODO: Some notion of flags

    def is_named(self, name):
        if self.field:
            if name in (self.field.name, self.field.def_num):
                return True
        if self.parent_field:
            if name in (self.parent_field.name, self.parent_field.def_num):
                return True
        if self.field_def:
            if name == self.field_def.def_num:
                return True
        return False

    @property
    def def_num(self):
        # Prefer to return the def_num on the field
        # since field_def may be None if this field is dynamic
        return self.field.def_num if self.field else self.field_def.def_num

    @property
    def base_type(self):
        # Try field_def's base type, if it doesn't exist, this is a
        # dynamically added field, so field doesn't be None
        return self.field_def.base_type if self.field_def else self.field.base_type

    @property
    def is_base_type(self):
        return self.field.is_base_type if self.field else True

    @property
    def type(self):
        return self.field.type if self.field else self.base_type

    @property
    def field_type(self):
        return self.field.field_type if self.field else 'field'

    def as_dict(self):
        return {
            'name': self.name, 'def_num': self.def_num, 'base_type': self.base_type.name,
            'type': self.type.name, 'units': self.units, 'value': self.value,
            'raw_value': self.raw_value,
        }

    def __repr__(self):
        return '<FieldData: %s: %s%s, def num: %d, type: %s (%s), raw value: %s>' % (
            self.name, self.value, ' [%s]' % self.units if self.units else '',
            self.def_num, self.type.name, self.base_type.name, self.raw_value,
        )

    def __str__(self):
        return '%s: %s%s' % (
            self.name, self.value, ' [%s]' % self.units if self.units else '',
        )


class BaseType(RecordBase):
    __slots__ = ('name', 'identifier', 'fmt', 'parse')
    values = None  # In case we're treated as a FieldType

    @property
    def size(self):
        return struct.calcsize(self.fmt)

    @property
    def type_num(self):
        return self.identifier & 0x1F

    def __repr__(self):
        return '<BaseType: %s (#%d [0x%X])>' % (
            self.name, self.type_num, self.identifier,
        )


class FieldType(RecordBase):
    __slots__ = ('name', 'base_type', 'values')

    def __repr__(self):
        return '<FieldType: %s (%s)>' % (self.name, self.base_type)


class MessageType(RecordBase):
    __slots__ = ('name', 'mesg_num', 'fields')

    def __repr__(self):
        return '<MessageType: %s (#%d)>' % (self.name, self.mesg_num)


class FieldAndSubFieldBase(RecordBase):
    __slots__ = ()

    @property
    def base_type(self):
        return self.type if self.is_base_type else self.type.base_type

    @property
    def is_base_type(self):
        return isinstance(self.type, BaseType)

    def render(self, raw_value):
        if self.type.values and (raw_value in self.type.values):
            return self.type.values[raw_value]
        return raw_value


class Field(FieldAndSubFieldBase):
    __slots__ = ('name', 'type', 'def_num', 'scale', 'offset', 'units', 'components', 'subfields')
    field_type = 'field'


class SubField(FieldAndSubFieldBase):
    __slots__ = ('name', 'def_num', 'type', 'scale', 'offset', 'units', 'components', 'ref_fields')
    field_type = 'subfield'


class DevField(FieldAndSubFieldBase):
    __slots__ = ('dev_data_index', 'def_num', 'type', 'name', 'units', 'native_field_num',
                 # The rest of these are just to be compatible with Field objects. They're always None
                 'scale', 'offset', 'components', 'subfields')
    field_type = 'devfield'


class ReferenceField(RecordBase):
    __slots__ = ('name', 'def_num', 'value', 'raw_value')


class ComponentField(RecordBase):
    __slots__ = ('name', 'def_num', 'scale', 'offset', 'units', 'accumulate', 'bits', 'bit_offset')
    field_type = 'component'

    def render(self, raw_value):
        if raw_value is None:
            return None

        # If it's a tuple, then it's a byte array and unpack it as such
        # (only type that uses this is compressed speed/distance)
        if isinstance(raw_value, tuple):
            # Profile.xls sometimes contains more components than the read raw
            # value is able to hold (typically the *event_timestamp_12* field in
            # *hr* messages).
            # This test allows to ensure *unpacked_num* is not right-shifted
            # more than necessary.
            if self.bit_offset and self.bit_offset >= len(raw_value) << 3:
                raise ValueError()

            unpacked_num = 0

            # Unpack byte array as little endian
            for value in reversed(raw_value):
                unpacked_num = (unpacked_num << 8) + value

            raw_value = unpacked_num

        # Mask and shift like a normal number
        if isinstance(raw_value, int_types):
            raw_value = (raw_value >> self.bit_offset) & ((1 << self.bits) - 1)

        return raw_value


class Crc(object):
    """FIT file CRC computation."""

    CRC_TABLE = (
        0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
        0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
    )

    FMT = 'H'

    def __init__(self, value=0, byte_arr=None):
        self.value = value
        if byte_arr:
            self.update(byte_arr)

    def __repr__(self):
        return '<%s %s>' % (self.__class__.__name__, self.value or "-")

    def __str__(self):
        return self.format(self.value)

    def update(self, byte_arr):
        """Read bytes and update the CRC computed."""
        if byte_arr:
            self.value = self.calculate(byte_arr, self.value)

    @staticmethod
    def format(value):
        """Format CRC value to string."""
        return '0x%04X' % value

    @classmethod
    def calculate(cls, byte_arr, crc=0):
        """Compute CRC for input bytes."""
        for byte in byte_iter(byte_arr):
            # Taken verbatim from FIT SDK docs
            tmp = cls.CRC_TABLE[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ cls.CRC_TABLE[byte & 0xF]

            tmp = cls.CRC_TABLE[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ cls.CRC_TABLE[(byte >> 4) & 0xF]
        return crc


def parse_string(string):
    try:
        try:
            s = string[:string.index(0x00)]
        except TypeError: # Python 2 compat
            s = string[:string.index('\x00')]
    except ValueError:
        # FIT specification defines the 'string' type as follows: "Null
        # terminated string encoded in UTF-8 format".
        #
        # However 'string' values are not always null-terminated when encoded,
        # according to FIT files created by Garmin devices (e.g. DEVICE.FIT file
        # from a fenix3).
        #
        # So in order to be more flexible, in case index() could not find any
        # null byte, we just decode the whole bytes-like object.
        s = string

    return s.decode(encoding='utf-8', errors='replace') or None

# The default base type
BASE_TYPE_BYTE = BaseType(name='byte', identifier=0x0D, fmt='B', parse=lambda x: None if all(b == 0xFF for b in x) else x)

BASE_TYPES = {
    0x00: BaseType(name='enum', identifier=0x00, fmt='B', parse=lambda x: None if x == 0xFF else x),
    0x01: BaseType(name='sint8', identifier=0x01, fmt='b', parse=lambda x: None if x == 0x7F else x),
    0x02: BaseType(name='uint8', identifier=0x02, fmt='B', parse=lambda x: None if x == 0xFF else x),
    0x83: BaseType(name='sint16', identifier=0x83, fmt='h', parse=lambda x: None if x == 0x7FFF else x),
    0x84: BaseType(name='uint16', identifier=0x84, fmt='H', parse=lambda x: None if x == 0xFFFF else x),
    0x85: BaseType(name='sint32', identifier=0x85, fmt='i', parse=lambda x: None if x == 0x7FFFFFFF else x),
    0x86: BaseType(name='uint32', identifier=0x86, fmt='I', parse=lambda x: None if x == 0xFFFFFFFF else x),
    0x07: BaseType(name='string', identifier=0x07, fmt='s', parse=parse_string),
    0x88: BaseType(name='float32', identifier=0x88, fmt='f', parse=lambda x: None if math.isnan(x) else x),
    0x89: BaseType(name='float64', identifier=0x89, fmt='d', parse=lambda x: None if math.isnan(x) else x),
    0x0A: BaseType(name='uint8z', identifier=0x0A, fmt='B', parse=lambda x: None if x == 0x0 else x),
    0x8B: BaseType(name='uint16z', identifier=0x8B, fmt='H', parse=lambda x: None if x == 0x0 else x),
    0x8C: BaseType(name='uint32z', identifier=0x8C, fmt='I', parse=lambda x: None if x == 0x0 else x),
    0x0D: BASE_TYPE_BYTE,
    0x8E: BaseType(name='sint64', identifier=0x8E, fmt='q', parse=lambda x: None if x == 0x7FFFFFFFFFFFFFFF else x),
    0x8F: BaseType(name='uint64', identifier=0x8F, fmt='Q', parse=lambda x: None if x == 0xFFFFFFFFFFFFFFFF else x),
    0x90: BaseType(name='uint64z', identifier=0x90, fmt='Q', parse=lambda x: None if x == 0 else x),
}


def add_dev_data_id(message):
    global DEV_TYPES
    dev_data_index = message.get_raw_value('developer_data_index')
    application_id = message.get_raw_value('application_id')

    # Note that nothing in the spec says overwriting an existing type is invalid
    DEV_TYPES[dev_data_index] = {'dev_data_index': dev_data_index, 'application_id': application_id, 'fields': {}}


def add_dev_field_description(message):
    global DEV_TYPES

    dev_data_index = message.get_raw_value('developer_data_index')
    field_def_num = message.get_raw_value('field_definition_number')
    base_type_id = message.get_raw_value('fit_base_type_id')
    field_name = message.get_raw_value('field_name') or "unnamed_dev_field_%s" % field_def_num
    units = message.get_raw_value("units")
    native_field_num = message.get_raw_value('native_field_num')

    if dev_data_index not in DEV_TYPES:
        raise FitParseError("No such dev_data_index=%s found" % (dev_data_index))
    fields = DEV_TYPES[int(dev_data_index)]['fields']

    # Note that nothing in the spec says overwriting an existing field is invalid
    fields[field_def_num] = DevField(dev_data_index=dev_data_index,
                                     def_num=field_def_num,
                                     type=BASE_TYPES[base_type_id],
                                     name=field_name,
                                     units=units,
                                     native_field_num=native_field_num)


def get_dev_type(dev_data_index, field_def_num):
    if dev_data_index not in DEV_TYPES:
        raise FitParseError("No such dev_data_index=%s found when looking up field %s" % (dev_data_index, field_def_num))
    elif field_def_num not in DEV_TYPES[dev_data_index]['fields']:
        raise FitParseError("No such field %s for dev_data_index %s" % (field_def_num, dev_data_index))

    return DEV_TYPES[dev_data_index]['fields'][field_def_num]
