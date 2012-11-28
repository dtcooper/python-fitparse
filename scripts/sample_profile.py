from collections import namedtuple


# Bare minimum profile.py to make generate_profile.py work

FieldType = namedtuple('FieldType', ('name', 'base_type', 'values'))
MessageType = namedtuple('MessageType', ('name', 'mesg_num', 'fields'))
Field = namedtuple('Field', ('name', 'type', 'num', 'scale', 'offset', 'units', 'components', 'sub_fields'))
SubField = namedtuple('SubField', ('name', 'type', 'scale', 'offset', 'units', 'ref_fields'))
ReferenceField = namedtuple('ReferenceField', ('name', 'num', 'value'))
ComponentField = namedtuple('ComponentField', ('name', 'num', 'scale', 'offset', 'units', 'accumulate', 'bits'))


# TODO, 13 base types
BASE_TYPES = dict((k, 'TODO') for k in range(14))
