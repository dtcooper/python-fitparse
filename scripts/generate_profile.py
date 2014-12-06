#!/usr/bin/env python

#
# Extremely crude script that I'm not at all proud of. Generate
# fitparse/profile.def from the Profile.xls definition file that comes with
# the FIT SDK. You shouldn't have to run this, since I've included an
# automatically generated profile.dif file.
#
# (NOTE: it'll probably break on any version of the FIT SDK that isn't 1.2)
#

# TODO: Units override code -- for at least,
#  * date_time -- it's "s" now, want None
#  * compressed_speed_distance -- it's "m/s,\nm", probably want None

from collections import namedtuple
import datetime
import os
import sys

import xlrd


def banner_str(s):
    return ("   %s   " % s).center(BANNER_PADDING, '#')


# TODO: Maybe make a copyright, or more info about this program/library?
BANNER_PADDING = 78
PROFILE_OUTPUT_FILE_HEADER_MAGIC = '%s\n%s\n%s' % (
    '#' * BANNER_PADDING,
    banner_str('AUTOMATICALLY GENERATED DEFINITION FILE'),
    '#' * BANNER_PADDING,
)

PROFILE_OUTPUT_FILE_HEADER_FMT = '''%s
#
# %%s -- Exported FIT SDK Profile Data
# Created on %%s by %%s from %%s
#
''' % PROFILE_OUTPUT_FILE_HEADER_MAGIC


# Using namedtuples for convience. These have absolutely nothing to do with the
# ones in found in fitparse.records, other than Field and DynamicField which
# are the similar to their counterparts in records.py by coincidence

Field = namedtuple('Field', ('name', 'type', 'scale', 'units', 'offset'))
DynamicField = namedtuple('DynamicField', ('name', 'type', 'scale', 'units', 'offset', 'possibilities'))
# Type.values can be a str, (ie, a lambda or the name of a function defined in records.py)
Type = namedtuple('Type', ('name', 'base_type', 'values'))
TypeValue = namedtuple('TypeValue', ('name', 'value'))
SpecialFunctionType = namedtuple('SpecialFunctionType', ('name', 'base_type', 'func_name'))

FIELD_BASE_TYPES = {
    'enum': 0,
    'sint8': 1,
    'uint8': 2,
    'sint16': 3,
    'uint16': 4,
    'sint32': 5,
    'uint32': 6,
    'string': 7,
    'float32': 8,
    'float64': 9,
    'uint8z': 10,
    'uint16z': 11,
    'uint32z': 12,
    'byte': 13,
}

## Special fields in messages -- syntax "<message_name>-<field_name>"
SPECIAL_TYPES = {
    # '[<message_name>-]<field_name>': SpecialFunctionType('<base_type>', <function_str or None for default>),
    'bool': SpecialFunctionType('bool', 'enum', None),
    'record-compressed_speed_distance': SpecialFunctionType('record-compressed_speed_distance', 'byte', None),
}

# Same as SPECIAL_TYPES, but these will exist in the types dict after parse_fields()
SPECIAL_TYPES_IN_TYPES_SPREADSHEET = {
    'date_time': SpecialFunctionType('date_time', 'uint32', None),
    'local_date_time': SpecialFunctionType('local_date_time', 'uint32', None),
    'message_index': SpecialFunctionType('message_index', 'uint16', None),
    'activity_class': SpecialFunctionType('activity_class', 'enum', None),
}

SPECIAL_TYPES_ALL = dict(SPECIAL_TYPES.items() + SPECIAL_TYPES_IN_TYPES_SPREADSHEET.items())

if len(sys.argv) <= 1 or not os.path.exists(sys.argv[1]):
    print "Usage: %s <Profile.xls> [profile.def]" % os.path.basename(sys.argv[0])
    sys.exit(0)

profile_xls_filename = sys.argv[1]
workbook = xlrd.open_workbook(profile_xls_filename)

write_buffer = ""


def write(s):
    global write_buffer
    write_buffer += str(s)


def writeln(s=''):
    write(str(s) + "\n")


def parse_types():
    # Go through Types workbook

    types_sheet = workbook.sheet_by_name('Types')
    types = {}

    for row in range(1, types_sheet.nrows):
        row_values = [str(v).strip() if isinstance(v, (str, unicode)) else v \
                      for v in types_sheet.row_values(row, end_colx=4)]

        if not any(row_values):
            continue

        possible_type_name, possible_base_type, name, value = row_values

        if possible_type_name:
            type_name = possible_type_name
            base_type = possible_base_type

        if possible_type_name:
            # We define a type here
            types[type_name] = Type(type_name, base_type, {})

        elif name:
            if 'int' in base_type or base_type == 'enum':
                # Convert value to int if required
                if type(value) == float and value % 1 == 0.0:
                    value = int(value)

            types[type_name].values[value] = TypeValue(name, value)

    types.update(SPECIAL_TYPES)

    # Special considerations on types dict

    ## FOR NOW: skip mfg_range_min (0xFF00) and mfg_range_max (0xFFFE)
    for value in [v.value for v in types['mesg_num'].values.copy().itervalues()
                  if v.name in ('mfg_range_min', 'mfg_range_max')]:
        del types['mesg_num'].values[value]

    return types


### Go through Message workbook ###

def parse_fields():
    messages_sheet = workbook.sheet_by_name('Messages')

    fields = {}
    last_field = None
    last_f_def_num = None

    for row in range(1, messages_sheet.nrows):
        row_values = [str(v).strip() if isinstance(v, (str, unicode)) else v \
                      for v in messages_sheet.row_values(row, end_colx=4)]

        # Skip blank rows
        if not any(row_values):
            continue

        # Check if it's a seperator row, ie only third column
        if not any(row_values[:3]) and row_values[3]:
            # TODO: here row_values[3] describes what file type these messages belong to
            continue

        possible_message_name, f_def_num, f_name, f_type = row_values

        if possible_message_name:
            # Define a message here
            message_name = possible_message_name
            fields[message_name] = {}
        else:
            # Sip for now unless all rows are here
            if not (message_name and f_name and f_type):
                pass
            else:

                is_dynamic_field = False

                try:
                    f_def_num = int(f_def_num)
                except ValueError:
                    # f_def_num not defined, we have a dynamic field on last_field
                    is_dynamic_field = True

                    if not isinstance(last_field, DynamicField):
                        last_field = DynamicField(*(tuple(last_field) + ({},)))
                        fields[message_name][last_f_def_num] = last_field

                    ref_field_names = [str(n).strip() for n in messages_sheet.row_values(row)[11].split(',')]
                    ref_field_values = [str(n).strip() for n in messages_sheet.row_values(row)[12].split(',')]

                    if len(ref_field_names) != len(ref_field_values):
                        raise Exception("Number of ref fields != number of ref values for %s" % f_name)

                try:
                    f_scale = int(messages_sheet.row_values(row)[6])
                    if f_scale == 1:
                        raise ValueError
                except ValueError:
                    f_scale = None

                try:
                    f_offset = int(messages_sheet.row_values(row)[7])
                except ValueError:
                    f_offset = None

                f_units = str(messages_sheet.row_values(row)[8]).strip()
                if not f_units:
                    f_units = None

                field = Field(f_name, f_type, f_scale, f_units, f_offset)

                if is_dynamic_field:
                    for i in range(len(ref_field_names)):
                        last_field.possibilities.setdefault(ref_field_names[i], {})[ref_field_values[i]] = field

                else:
                    fields[message_name][f_def_num] = field
                    last_field = field
                    last_f_def_num = f_def_num

    # Special considerations on fields dict

    # Copy possiblities for event.data into event.data16
    event = fields['event']
    for k, v in event.iteritems():
        if v.name == 'data':
            data_num = k
        elif v.name == 'data16':
            data16_num = k
    try:
        event[data16_num] = DynamicField(*tuple(event[data16_num] + (event[data_num].possibilities.copy(),)))
    except NameError:
        raise Exception("Couldn't find fields data/data16 in message type event")

    return fields


def autogen_python(types, fields):
    global write_buffer

    functions = {}

    writeln("\n%s\n" % banner_str('BEGIN FIELD TYPES'))

    for _, type in sorted(types.iteritems()):

        write("FieldType(%s, FieldTypeBase(%s), " % (repr(type.name), FIELD_BASE_TYPES[type.base_type]))

        if type.name in SPECIAL_TYPES_ALL:
            special_type = SPECIAL_TYPES_ALL[type.name]
            if type.base_type != special_type.base_type:
                raise Exception("Type misatch on '%s'" % type.name)

            func_name = special_type.func_name
            if not special_type.func_name:
                func_name = '_convert_%s' % type.name.replace('-', '_')
            functions.setdefault(func_name, []).append(type.name)

            writeln("%s)  # base type: %s\n" % (func_name, type.base_type))

        else:
            writeln("{  # base type: %s" % type.base_type)
            for _, value in sorted(type.values.iteritems()):
                writeln("    %s: %s," % (value.value, repr(value.name)))
            writeln("})\n")

    writeln("\n%s\n" % banner_str('BEGIN MESSAGE TYPES'))

    for msg_num, message in sorted(types['mesg_num'].values.iteritems()):
        msg_name = message.name

        writeln("MessageType(%s, %s, {" % (msg_num, repr(msg_name)))

        msg_fields = fields[msg_name]
        for f_num, field in sorted(msg_fields.iteritems()):
            write("    %s: " % f_num)

            def field_gen(field):
                is_base_type = False
                is_special_function_type = False
                write("%s(%s, " % (field.__class__.__name__, repr(field.name)))

                special_type_name = "%s-%s" % (msg_name, field.name)
                # Predefined type
                if field.type in types or special_type_name in types:
                    type_name = field.type
                    special_type = SPECIAL_TYPES_ALL.get(special_type_name)
                    if special_type:
                        type_name = special_type_name
                        is_special_function_type = True
                        if special_type.base_type != field.type:
                            raise Exception("Type misatch on '%s'" % field.name)

                    write("FieldType(%s)," % repr(type_name))

                # Base type
                elif field.type in FIELD_BASE_TYPES:
                    write("FieldTypeBase(%s)," % FIELD_BASE_TYPES[field.type])
                    is_base_type = True
                else:
                    raise Exception("Unknown field type: %s" % field.type)

                write(" %s, %s, %s" % (
                    repr(field.units), repr(field.scale), repr(field.offset)))

                if isinstance(field, DynamicField):
                    write(", {")
                else:
                    write('),')

                write("  # base type: ")
                if is_base_type or is_special_function_type:
                    writeln(field.type)
                else:
                    writeln(types[field.type].base_type)

            field_gen(field)

            if isinstance(field, DynamicField):
                for ref_name, dynamic_fields in field.possibilities.iteritems():
                    writeln('        %s: {' % repr(ref_name))
                    for ref_value, dynamic_field in dynamic_fields.iteritems():
                        write('            %s: ' % repr(ref_value))
                        field_gen(dynamic_field)
                    writeln('        },')
                writeln('    }),')
        writeln("})\n")

    writeln("\n%s\n" % banner_str('DELETE CONVERSION FUNCTIONS'))

    for func in sorted(set(functions.iterkeys())):
        writeln("del %s" % func)

    writeln("\n\n%s" % banner_str('AUTOGENERATION COMPLETE'))

    # Prepend a required functions header to write_buffer
    req_func_out = '#' * BANNER_PADDING + "\n#\n"
    req_func_out += "# Please define the following functions (types that use them are listed):\n#\n"
    for func_name, type_names in sorted(functions.iteritems()):
        req_func_out += "#  %s\n" % func_name
        req_func_out += "#    * Used by types:\n"
        for type_name in type_names:
            req_func_out += "#       - %s\n" % type_name
        req_func_out += '#\n'
    req_func_out += ('#' * BANNER_PADDING) + "\n\n"

    write_buffer = req_func_out + write_buffer


def main():
    global write_buffer

    profile_output_filename = None

    if len(sys.argv) >= 3:
        profile_output_filename = sys.argv[2]

        if os.path.exists(profile_output_filename):
            old_profile = open(profile_output_filename, 'r').read()
            if PROFILE_OUTPUT_FILE_HEADER_MAGIC not in old_profile:
                print "Couldn't find header in %s. Exiting." % profile_output_filename
                sys.exit(1)
            del old_profile

        # Generate header
        profile_header = PROFILE_OUTPUT_FILE_HEADER_FMT % (
            os.path.basename(profile_output_filename),
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            os.path.basename(__file__),
            os.path.basename(profile_xls_filename),
        )

    if profile_output_filename:
        print "Generating profile from %s" % profile_xls_filename

    types = parse_types()
    fields = parse_fields()

    autogen_python(types, fields)

    if profile_output_filename:
        print "Writing to %s" % profile_output_filename
        profile_output_file = open(profile_output_filename, 'w')
        copyright_header = open(os.path.abspath(__file__)).readlines()
        copyright_header = (''.join(copyright_header[1:copyright_header.index('\n')])).strip()
        profile_output_file.write(copyright_header + "\n\n\n")
        profile_output_file.write(profile_header)
        profile_output_file.write(write_buffer)
        profile_output_file.close()
    else:
        print write_buffer


if __name__ == '__main__':
    main()
