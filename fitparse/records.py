import itertools
import math
import struct

try:
    # Python 2
    int_types = (int, long,)
    num_types = (int, float, long)
    int_type = long
    math_nan = float('nan')
    byte_iter = bytearray
except NameError:
    # Python 3
    int_types = (int,)
    num_types = (int, float)
    int_type = int
    math_nan = math.nan
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
        return '<DefinitionMessage: %s (#%s) -- local mesg: #%s, field defs: [%s], dev field defs: [%s]>' % (
            self.name,
            self.mesg_num,
            self.header.local_mesg_num,
            ', '.join([fd.name for fd in self.field_defs]),
            ', '.join([fd.name for fd in self.dev_field_defs]),
        )

    def all_field_defs(self):
        if not self.dev_field_defs:
            return self.field_defs
        return itertools.chain(self.field_defs, self.dev_field_defs)

    def get_field_def(self, name):
        for field_def in self.all_field_defs():
            if field_def.is_named(name):
                return field_def
        return None


class FieldDefinition(RecordBase):
    __slots__ = ('field', 'def_num', 'base_type', 'size')

    @property
    def name(self):
        return self.field.name if self.field else 'unknown_%d' % self.def_num

    @property
    def type(self):
        return self.field.type if self.field else self.base_type

    def __repr__(self):
        return '<FieldDefinition: %s (#%s) -- type: %s (%s), size: %s byte%s>' % (
            self.name,
            self.def_num,
            self.type.name, self.base_type.name,
            self.size, 's' if self.size != 1 else '',
        )

    def is_named(self, name):
        return self.field.is_named(name)



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
        return '<DataMessage: %s (#%s) -- local mesg: #%s, fields: [%s]>' % (
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


class BaseType(object):
    __slots__ = ('name', 'identifier', 'fmt', 'invalid_value', 'parse', 'unparse', 'in_range', '_size')
    values = None  # In case we're treated as a FieldType

    def __init__(self, name, identifier, fmt, invalid_value=None, parse=None, unparse=None, in_range=None):
        self.name = name
        self.identifier = identifier
        self.fmt = fmt
        self.invalid_value = invalid_value
        self.parse = parse or self._parse
        self.unparse = unparse or self._unparse
        self.in_range = in_range or self._in_range
        self._size = None

    @property
    def size(self):
        if self._size is None:
            self._size = struct.calcsize(self.fmt)
        return self._size

    @property
    def type_num(self):
        return self.identifier & 0x1F

    def __repr__(self):
        return '<BaseType: %s (#%d [0x%X])>' % (
            self.name, self.type_num, self.identifier,
        )

    def _parse(self, x):
        return None if x == self.invalid_value else x

    def _unparse(self, x):
        return self.invalid_value if x is None else x

    def _in_range(self, x):
        # basic implementation for int types
        return self.invalid_value if x.bit_length() > self.size * 8 else x



class FieldType(RecordBase):
    __slots__ = ('name', 'base_type', 'values')

    def __repr__(self):
        return '<FieldType: %s (%s)>' % (self.name, self.base_type)


class MessageType(RecordBase):
    __slots__ = ('name', 'mesg_num', 'fields')

    def __repr__(self):
        return '<MessageType: %s (#%d)>' % (self.name, self.mesg_num)

    def get_field_and_subfield(self, name):
        """
        Get field by name.
        :rtype tuple(Field, SubField) or tuple(Field, None) or (None, None)
        """
        for field in self.fields.values():
            if field.is_named(name):
                return (field, None)
            if field.subfields:
                subfield = next((f for f in field.subfields if f.is_named(name)), None)
                if subfield:
                    return (field, subfield)

        return (None, None)


class ScaleOffsetMixin(object):
    """Common methods for classes with scale and offset."""

    def apply_scale_offset(self, raw_value):
        if isinstance(raw_value, tuple):
            # Contains multiple values, apply transformations to all of them
            return tuple(self.apply_scale_offset(x) for x in raw_value)
        elif isinstance(raw_value, num_types):
            if self.scale:
                raw_value = float(raw_value) / self.scale
            if self.offset:
                raw_value = raw_value - self.offset
        return raw_value

    def unapply_scale_offset(self, value):
        if isinstance(value, tuple):
            # Contains multiple values, apply transformations to all of them
            return tuple(self.unapply_scale_offset(x) for x in value)
        elif isinstance(value, num_types):
            if self.offset:
                value = value + self.offset
            if self.scale:
                value = float(value) * self.scale
            if isinstance(value, float):
                value = int_type(round(value))
        return value


class FieldAndSubFieldBase(RecordBase, ScaleOffsetMixin):
    __slots__ = ()

    @property
    def base_type(self):
        return self.type if self.is_base_type else self.type.base_type

    @property
    def is_base_type(self):
        return isinstance(self.type, BaseType)

    def __repr__(self):
        return '<%s: %s (#%s) -- type: %s (%s)>' % (
            self.__class__.__name__,
            self.name,
            self.def_num,
            self.type.name,
            self.base_type
        )

    def is_named(self, name):
        return self.name == name or self.def_num == name

    def render(self, raw_value):
        if self.type.values:
            return self.type.values.get(raw_value, raw_value)
        return raw_value

    def unrender(self, raw_value):
        if self.type.values:
            return next((k for k, v in self.type.values.items() if v == raw_value), raw_value)
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


class ComponentField(RecordBase, ScaleOffsetMixin):
    __slots__ = ('name', 'def_num', 'scale', 'offset', 'units', 'accumulate', 'bits', 'bit_offset')
    field_type = 'component'

    def render(self, raw_value):
        if raw_value is None:
            return None

        # If it's a tuple, then it's a byte array and unpack it as such
        # (only type that uses this is compressed speed/distance)
        if isinstance(raw_value, tuple):
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
        end = string.index(0x00)
    except TypeError:  # Python 2 compat
        end = string.index('\x00')

    return string[:end].decode('utf-8', errors='replace') or None


def unparse_string(string):
    if string is None:
        string = ''
    sbytes = string.encode('utf-8', errors='replace') + b'\0'
    return sbytes


_FLOAT32_INVALID_VALUE = struct.unpack('f', bytes(b'\xff' * 4))[0]
_FLOAT32_MIN = -3.4028235e+38
_FLOAT32_MAX = 3.4028235e+38
_FLOAT64_INVALID_VALUE = struct.unpack('d', bytes(b'\xff' * 8))[0]

# The default base type
BASE_TYPE_BYTE = BaseType(name='byte', identifier=0x0D, fmt='B',
                          parse=lambda x: None if all(b == 0xFF for b in x) else x,
                          unparse=lambda x: b'\xFF' if x is None else x,
                          in_range=lambda x: x)

BASE_TYPES = {
    0x00: BaseType(name='enum', identifier=0x00, fmt='B', invalid_value=0xFF),
    0x01: BaseType(name='sint8', identifier=0x01, fmt='b', invalid_value=0x7F),
    0x02: BaseType(name='uint8', identifier=0x02, fmt='B', invalid_value=0xFF),
    0x83: BaseType(name='sint16', identifier=0x83, fmt='h', invalid_value=0x7FFF),
    0x84: BaseType(name='uint16', identifier=0x84, fmt='H', invalid_value=0xFFFF),
    0x85: BaseType(name='sint32', identifier=0x85, fmt='i', invalid_value=0x7FFFFFFF),
    0x86: BaseType(name='uint32', identifier=0x86, fmt='I', invalid_value=0xFFFFFFFF),
    0x07: BaseType(name='string', identifier=0x07, fmt='s', parse=parse_string, unparse=unparse_string, in_range=lambda x: x),
    0x88: BaseType(name='float32', identifier=0x88, fmt='f', invalid_value=_FLOAT32_INVALID_VALUE,
                   parse=lambda x: None if math.isnan(x) else x,
                   in_range=lambda x: x if _FLOAT32_MIN < x < _FLOAT32_MAX else _FLOAT32_INVALID_VALUE),
    0x89: BaseType(name='float64', identifier=0x89, fmt='d', invalid_value=_FLOAT64_INVALID_VALUE,
                   parse=lambda x: None if math.isnan(x) else x,
                   in_range=lambda x: x),
    0x0A: BaseType(name='uint8z', identifier=0x0A, fmt='B', invalid_value=0x0),
    0x8B: BaseType(name='uint16z', identifier=0x8B, fmt='H', invalid_value=0x0),
    0x8C: BaseType(name='uint32z', identifier=0x8C, fmt='I', invalid_value=0x0),
    0x0D: BASE_TYPE_BYTE,
}


def add_dev_data_id(message):
    global DEV_TYPES
    dev_data_index = message.get('developer_data_index').raw_value
    if message.get('application_id'):
        application_id = message.get('application_id').raw_value
    else:
        application_id = None

    # Note that nothing in the spec says overwriting an existing type is invalid
    DEV_TYPES[dev_data_index] = {'dev_data_index': dev_data_index, 'application_id': application_id, 'fields': {}}


def add_dev_field_description(message):
    global DEV_TYPES

    dev_data_index = message.get('developer_data_index').raw_value
    field_def_num = message.get('field_definition_number').raw_value
    base_type_id = message.get('fit_base_type_id').raw_value
    field_name = message.get('field_name').raw_value
    units = message.get('units').raw_value

    native_field_num = message.get('native_field_num')
    if native_field_num is not None:
        native_field_num = native_field_num.raw_value

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
