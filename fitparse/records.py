import math
import struct

# Python 2 compat
try:
    int_types = (int, long,)
except NameError:
    int_types = (int,)

try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest

from fitparse.utils import FitParseError

DEV_TYPES = {}


class MessageHeader(object):
    __slots__ = ('is_definition', 'is_developer_data', 'local_mesg_num', 'time_offset')

    def __init__(self, is_definition, is_developer_data, local_mesg_num, time_offset):
        self.is_definition = is_definition
        self.is_developer_data = is_developer_data
        self.local_mesg_num = local_mesg_num
        self.time_offset = time_offset

    def __repr__(self):
        return '<MessageHeader: %s%s -- local mesg: #%d%s>' % (
            'definition' if self.is_definition else 'data',
            '(developer)' if self.is_developer_data else '',
            self.local_mesg_num,
            ', time offset: %d' % self.time_offset if self.time_offset else '',
        )


class DefinitionMessage(object):
    __slots__ = ('header', 'endian', 'mesg_type', 'mesg_num', 'field_defs', 'dev_field_defs')
    type = 'definition'

    def __init__(self, header, endian, mesg_type, mesg_num, field_defs, dev_field_defs):
        self.header = header
        self.endian = endian
        self.mesg_type = mesg_type
        self.mesg_num = mesg_num
        self.field_defs = field_defs
        self.dev_field_defs = dev_field_defs

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


class FieldDefinition(object):
    __slots__ = ('field', 'def_num', 'base_type', 'size')

    def __init__(self, field, def_num, base_type, size):
        self.field = field
        self.def_num = def_num
        self.base_type = base_type
        self.size = size

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


class DevFieldDefinition(object):
    __slots__ = ('field', 'dev_data_index', 'base_type', 'def_num', 'size')

    def __init__(self, field, dev_data_index, def_num, size):
        self.field = field
        self.def_num = def_num
        self.dev_data_index = dev_data_index
        self.size = size
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


class DataMessage(object):
    __slots__ = ('header', 'def_mesg', 'fields')
    type = 'data'

    def __init__(self, header, def_mesg, fields):
        self.header = header
        self.def_mesg = def_mesg
        self.fields = fields

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
        return '<DataMessage: %s (#%d) -- local mesg: #%d, fields: [%s]>' % (
            self.name, self.mesg_num, self.header.local_mesg_num,
            ', '.join(["%s: %s" % (fd.name, fd.value) for fd in self.fields]),
        )

    def __str__(self):
        # SIMPLIFY: get rid of this
        return '%s (#%d)' % (self.name, self.mesg_num)


class FieldData(object):
    __slots__ = ('field_def', 'field', 'parent_field', 'value', 'raw_value', 'units')

    def __init__(self, field_def, field, parent_field, value, raw_value, units=None):
        self.field_def = field_def
        self.field = field
        self.parent_field = parent_field
        self.value = value
        self.raw_value = raw_value
        self.units = units
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
    __slots__ = ('name', 'identifier', 'fmt', 'parse', '_size')
    values = None  # In case we're treated as a FieldType

    def __init__(self, name, identifier, fmt, parse):
        self.name = name
        self.identifier = identifier
        self.fmt = fmt
        self.parse = parse
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


class FieldType(object):
    __slots__ = ('name', 'base_type', 'values')

    def __init__(self, name, base_type, values=None):
        self.name = name
        self.base_type = base_type
        self.values = values

    def __repr__(self):
        return '<FieldType: %s (%s)>' % (self.name, self.base_type)


class MessageType():
    __slots__ = ('name', 'mesg_num', 'fields')

    def __init__(self, name, mesg_num, fields):
        self.name = name
        self.mesg_num = mesg_num
        self.fields = fields

    def __repr__(self):
        return '<MessageType: %s (#%d)>' % (self.name, self.mesg_num)


class FieldAndSubFieldBase(object):
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

    def __init__(self, name, type, def_num, scale=None, offset=None, units=None, components=None, subfields=None):
        super(Field, self).__init__()
        self.name = name
        self.type = type
        self.def_num = def_num
        self.scale = scale
        self.offset = offset
        self.units = units
        self.components = components
        self.subfields = subfields


class SubField(FieldAndSubFieldBase):
    __slots__ = ('name', 'def_num', 'type', 'scale', 'offset', 'units', 'components', 'ref_fields')
    field_type = 'subfield'

    def __init__(self, name, def_num, type, scale=None, offset=None, units=None, components=None, ref_fields=None):
        super(SubField, self).__init__()
        self.name = name
        self.def_num = def_num
        self.type = type
        self.scale = scale
        self.offset = offset
        self.units = units
        self.components = components
        self.ref_fields = ref_fields


class DevField(FieldAndSubFieldBase):
    __slots__ = ('dev_data_index', 'name', 'def_num', 'type', 'units', 'native_field_num',
                 # The rest of these are just to be compatible with Field objects. They're always None
                 'scale', 'offset', 'components', 'subfields')
    field_type = 'devfield'

    def __init__(self, dev_data_index, name, def_num, type, units, native_field_num):
        super(DevField, self).__init__()
        self.dev_data_index = dev_data_index
        self.name = name
        self.def_num = def_num
        self.type = type
        self.units = units
        self.native_field_num = native_field_num
        self.scale = None
        self.offset = None
        self.components = None
        self.subfields = None


class ReferenceField(object):
    __slots__ = ('name', 'def_num', 'value', 'raw_value')

    def __init__(self, name, def_num, value, raw_value):
        self.name = name
        self.def_num = def_num
        self.value = value
        self.raw_value = raw_value


class ComponentField(object):
    __slots__ = ('name', 'def_num', 'scale', 'offset', 'units', 'accumulate', 'bits', 'bit_offset')
    field_type = 'component'

    def __init__(self, name, def_num, offset=None, scale=None, units=None, accumulate=None, bits=None, bit_offset=None):
        self.name = name
        self.def_num = def_num
        self.scale = scale
        self.units = units
        self.accumulate = accumulate
        self.bits = bits
        self.bit_offset = bit_offset
        self.offset = offset

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


def parse_string(string):
    try:
        end = string.index(0x00)
    except TypeError: # Python 2 compat
        end = string.index('\x00')

    return string[:end].decode('utf-8', errors='replace') or None

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
                                     name=field_name,
                                     def_num=field_def_num,
                                     type=BASE_TYPES[base_type_id],
                                     units=units,
                                     native_field_num=native_field_num)


def get_dev_type(dev_data_index, field_def_num):
    if dev_data_index not in DEV_TYPES:
        raise FitParseError("No such dev_data_index=%s found when looking up field %s" % (dev_data_index, field_def_num))
    elif field_def_num not in DEV_TYPES[dev_data_index]['fields']:
        raise FitParseError("No such field %s for dev_data_index %s" % (field_def_num, dev_data_index))

    return DEV_TYPES[dev_data_index]['fields'][field_def_num]
