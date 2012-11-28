#!/usr/bin/env python

#
# Horrible, dirty, ugly, awful, and terrible script to export the Profile.xls
# that comes with the FIT SDK to the Python data structures in profile.py. You
# shouldn't have to use this unless you're developing python-fitparse.
#
# You can download the SDK at http://www.thisisant.com/
#
# WARNING: This script is only known to work with FIT SDK version 5.00
#


import cStringIO as StringIO
import datetime
import os
import sys

import xlrd


def header(header, indent=0):
    return '\n'.join([
        "%s%s" % (' ' * indent, (' %s ' % line).center(78 - indent, '#'))
        for line in header.strip().splitlines()
    ]) + '\n'


PROFILE_HEADER = header(
    'DO NOT EDIT THIS LINE OR ANY LINE BELOW\n'
    'BEGIN AUTOMATICALLY GENERATED FIT PROFILE'
)

BASE_TYPES = {
    'enum': 0, 'sint8': 1, 'uint8': 2, 'sint16': 3, 'uint16': 4, 'sint32': 5,
    'uint32': 6, 'string': 7, 'float32': 8, 'float64': 9, 'uint8z': 10,
    'uint16z': 11, 'uint32z': 12, 'byte': 13,
}

IGNORE_TYPE_VALUES = (
    # of the form 'type_name:value_name'
    'mesg_num:mfg_range_min',
    'mesg_num:mfg_range_max',
    'date_time:min',  # TODO: How to account for this (see Profile.xls)
)


def parse_field(data, fix_hint=None):
    if isinstance(data, basestring):
        data = data.strip()
        if data == '':
            data = None
        elif data.isdigit():
            data = int(data)
    else:
        data = int(data)

    # Hints to fix specific fields
    #TODO: Put this in second fix* pass
    if fix_hint is not None:
        if fix_hint == 'scale':
            if data == 1:
                data = None
        elif fix_hint == 'units':
            if data == 'kcal / min':
                data = 'kcal/min'
        elif fix_hint == 'accumulate':
            data = bool(data)
        else:
            raise Exception("Invalid unit hint: %s" % fix_hint)

    return data


def parse_csv_fields(data, num_expected_if_empty=None, fix_hint=None):
    if isinstance(data, basestring):
        values = [parse_field(x, fix_hint) for x in data.strip().split(',')]
        if num_expected_if_empty is not None:
            if len(values) == 1 and values[0] is None:
                return [None] * num_expected_if_empty
        return values
    else:
        return [parse_field(data, fix_hint)]


def parse_types_sheet(workbook):
    sheet = workbook.sheet_by_name('Types')
    types = []

    # Skip first row (it's a header)
    for row_number in range(1, sheet.nrows):
        row = sheet.row_values(row_number)

        # Ignore empty rows
        if all([x == '' for x in row]):
            continue

        if row[0]:
            # First column means a new type
            type_name = parse_field(row[0])
            type_info = {
                'name': type_name,
                'base_type': parse_field(row[1]),
                'values': [],
                'comment': parse_field(row[4]),
            }

            types.append(type_info)
            type_values = type_info['values']

            assert type_name
            assert type_info['base_type']
        else:
            # No first column means its a value for this type
            value_name = parse_field(row[2])

            # Calcualte ignore key and exlude if necessary
            ignore_key = "%s:%s" % (type_name, value_name)
            if ignore_key not in IGNORE_TYPE_VALUES:
                value_info = {
                    'name': value_name,
                    'value': parse_field(row[3]),
                    'comment': parse_field(row[4]),
                }
                type_values.append(value_info)

                assert value_name
                assert value_info['value'] is not None

    # Fixups and miscellany
    types_names_map = dict((ti['name'], ti) for ti in types)
    mesg_nums = dict(
        (vi['name'], vi['value']) for vi in types_names_map['mesg_num']['values']
    )
    if 'bool' not in types_names_map:
        # Add missing boolean type if it's not there
        types.append({
            'name': 'bool',
            'base_type': 'uint8',
        })

    return types, mesg_nums


def parse_messages_sheet(workbook, mesg_nums):
    sheet = workbook.sheet_by_name('Messages')
    messages = []

    for row_number in range(1, sheet.nrows):
        row = sheet.row_values(row_number)[:14]  # Ignore beyond 13th column

        # Ignore empty rows
        if all([x == '' for x in row]):
            continue

        if row[3] and all([x == '' for x in row[:2] + row[4:]]):
            # Only row 3 specified a new group of messages
            group_name = parse_field(row[3]).title()

        elif row[0]:
            # First column means a new message
            assert group_name

            message_name = parse_field(row[0])
            message_info = {
                'name': message_name,
                'group_name': group_name,
                'fields': [],
                'comment': parse_field(row[13]),
            }

            message_info['message_number'] = mesg_nums[message_name]

            messages.append(message_info)
            message_fields = message_info['fields']

            assert message_name
        else:
            # Dynamic field if 1st column is an empty string
            is_sub_field = bool(parse_field(row[1]) is None)

            if not is_sub_field:
                field_def_num = parse_field(row[1])

            field_info = {
                'name': parse_field(row[2]),
                'type': parse_field(row[3]),
                'comment': parse_field(row[13]),
            }

            if not is_sub_field:
                # Regular fields, is no subfields
                field_info['definition_number'] = field_def_num

            components = parse_csv_fields(row[5], 0)
            if not components:
                # Deal with a normal field, ie no components
                field_info.update({
                    'scale': parse_field(row[6], 'scale'),
                    'offset': parse_field(row[7]),
                    'units': parse_field(row[8], 'units'),
                })
            else:
                assert not is_sub_field  # Component fields shouldn't be subfields

                # Generate the list of component fields
                field_info['component_fields'] = [
                    {
                        'field_name': c_field_name,
                        'scale': c_scale,
                        'offset': c_offset,
                        # Todo are units needed or are they repeated in referenced field?
                        'units': c_units,
                        'bits': c_bits,
                        'accumulate': c_accumulate,
                    }
                    for c_field_name, c_scale, c_offset, c_units, c_bits, c_accumulate
                    in zip(
                        components,
                        parse_csv_fields(row[6], len(components), 'scale'),
                        parse_csv_fields(row[7], len(components)),
                        parse_csv_fields(row[8], len(components), 'units'),
                        parse_csv_fields(row[9], len(components)),
                        parse_csv_fields(row[10], len(components), 'accumulate'),
                    )
                ]

                assert len(field_info['component_fields']) == len(components)
                for component_info in field_info['component_fields']:
                    assert component_info['field_name']
                    assert component_info['bits']

            # If it's not a subfield, store the field and continue
            if not is_sub_field:
                message_fields.append(field_info)
            else:
                # If it's a sub-field, list what reference fields will trigger it
                ref_field_names = parse_csv_fields(row[11])
                ref_field_values = parse_csv_fields(row[12])

                field_info['reference_fields'] = [
                    {
                        'field_name': ref_field_name,
                        'field_value': ref_field_value,
                    }
                    for ref_field_name, ref_field_value
                    in zip(ref_field_names, ref_field_values)
                ]

                # Append it the sub-field list of the last regular field
                message_fields[-1].setdefault('sub_fields', []).append(field_info)

                assert len(ref_field_names) == len(ref_field_values)
                assert field_info['reference_fields']

    for message_info in messages:
        message_info['names_to_definition_nums'] = dict(
            (field_info['name'], field_info['definition_number'])
            for field_info in message_info['fields']
        )

    return messages


def render_comment(comment):
    if comment:
        return '  # %s' % comment
    return ''


def render_value(value):
    if isinstance(value, basestring):
        return "'%s'" % value
    return str(value)


def render_str(value):
    if value is None:
        return 'None'
    return value


def print_types(types, stream=None):
    print >> stream, "FIELD_TYPES = {"
    for type_info in sorted(types, key=lambda ti: ti['name']):
        values = type_info.get('values')
        print >> stream, "    '%s': FieldType(%s" % (
            type_info['name'], render_comment(type_info.get('comment')),
        )
        print >> stream, "        name='%s'," % type_info['name']
        print >> stream, "        base_type=BASE_TYPES[%d],  # %s" % (
            BASE_TYPES[type_info['base_type']],
            type_info['base_type'],
        )
        # Print values if they exist
        if values:
            print >> stream, "        values={"
            for value_info in sorted(values, key=lambda vi: vi['value']):
                print >> stream, "            %s: '%s',%s" % (
                    value_info['value'], value_info['name'],
                    render_comment(value_info['comment']),
                )
            print >> stream, "        },"
        else:
            print >> stream, "        values=None,"
        print >> stream, "     ),"
    print >> stream, "}"


def print_messages(messages, stream=None):
    print >> stream, "MESSAGE_TYPES = {"
    last_group_name = None

    for message_info in sorted(
        messages,
        key=lambda mi: "%s-%s-%05d" % (
            # sort common messages first, then group name, then name
            '0' if mi['group_name'].lower().startswith('common') else '1',
            mi['group_name'].lower(),
            mi['message_number'],
        ),
    ):
        # Print group name as a comment if it's new
        if last_group_name != message_info['group_name']:
            if last_group_name is not None:
                print >> stream, "\n"
            print >> stream, header(message_info['group_name'], 4)
            last_group_name = message_info['group_name']

        print >> stream, "    %d: MessageType(%s" % (
            message_info['message_number'],
            render_comment(message_info['comment']),
        )
        print >> stream, "        name='%s'," % message_info['name']
        print >> stream, "        mesg_num=%d," % message_info['message_number']
        print >> stream, "        fields={"
        for field_info in sorted(message_info['fields'], key=lambda fi: fi['definition_number']):
            print >> stream, "            %s: Field(%s" % (
                field_info['definition_number'], render_comment(field_info['comment']),
            )
            print >> stream, "                name='%s'," % field_info['name']
            if field_info['type'] in BASE_TYPES:
                print >> stream, "                type=BASE_TYPES[%d],  # %s" % (
                    BASE_TYPES[field_info['type']], field_info['type'],
                )
            else:
                print >> stream, "                type=FIELD_TYPES['%s']," % (
                    field_info['type']
                )
            print >> stream, "                num=%d," % field_info['definition_number']
            print >> stream, "                scale=%s," % field_info.get('scale')
            print >> stream, "                offset=%s," % field_info.get('offset')
            print >> stream, "                units=%s," % render_value(field_info.get('units'))
            if field_info.get('component_fields'):
                print >> stream, "                components=("
                for component_info in field_info['component_fields']:
                    print >> stream, "                    ComponentField("
                    print >> stream, "                        name='%s'," % component_info['field_name']
                    print >> stream, "                        num=%d," % (
                        message_info['names_to_definition_nums'][component_info['field_name']],
                    )
                    print >> stream, "                        scale=%s," % component_info.get('scale')
                    print >> stream, "                        offset=%s," % component_info.get('offset')
                    print >> stream, "                        units=%s," % render_value(component_info.get('units'))
                    print >> stream, "                        accumulate=%s," % component_info['accumulate']
                    print >> stream, "                        bits=%d," % component_info['bits']
                    print >> stream, "                    ),"
                print >> stream, "                ),"
                print >> stream, "                sub_fields=None,"
            else:
                print >> stream, "                components=None,"
                if field_info.get('sub_fields'):
                    print >> stream, "                sub_fields=("
                    for sub_field_info in sorted(field_info['sub_fields'], key=lambda sfi: sfi['name']):
                        print >> stream, "                    SubField(%s" % render_comment(sub_field_info['comment'])
                        print >> stream, "                        name='%s'," % sub_field_info['name']
                        if sub_field_info['type'] in BASE_TYPES:
                            print >> stream, "                        type=BASE_TYPES[%d],  # %s" % (
                                BASE_TYPES[sub_field_info['type']], sub_field_info['type'],
                            )
                        else:
                            print >> stream, "                        type=FIELD_TYPES['%s']," % (
                                sub_field_info['type']
                            )
                        print >> stream, "                        scale=%s," % sub_field_info.get('scale')
                        print >> stream, "                        offset=%s," % sub_field_info.get('offset')
                        print >> stream, "                        units=%s," % render_value(sub_field_info.get('units'))
                        print >> stream, "                        ref_fields=("
                        for reference_info in sub_field_info['reference_fields']:
                            print >> stream, "                            ReferenceField("
                            print >> stream, "                                name='%s'," % reference_info['field_name']
                            print >> stream, "                                num=%s," % (
                                message_info['names_to_definition_nums'][reference_info['field_name']],
                            )
                            print >> stream, "                                value='%s'," % reference_info['field_value']
                            print >> stream, "                            ),"
                        print >> stream, "                        ),"
                        print >> stream, "                    ),"
                    print >> stream, "                ),"
                else:
                    print >> stream, "                sub_fields=None,"
            print >> stream, "            ),"
        print >> stream, "        },"
        print >> stream, "    ),"

    print >> stream, "}"


def main():
    if len(sys.argv) < 2:
        print "Usage: %s Profile.xls [profile.py]" % os.path.basename(__file__)
        sys.exit(0)

    profile_xls_filename = sys.argv[1]
    profile_py_filename = sys.argv[2] if len(sys.argv) >= 3 else None
    output_stream = None

    workbook = xlrd.open_workbook(profile_xls_filename)
    types, mesg_nums = parse_types_sheet(workbook)
    messages = parse_messages_sheet(workbook, mesg_nums)

    if profile_py_filename:
        profile_py = open(profile_py_filename, 'r').read()
        header_pos = profile_py.find(PROFILE_HEADER)

        if header_pos != -1:
            profile_py = profile_py[:header_pos + len(PROFILE_HEADER)]
        else:
            print "WARNING: autogen header not found in %s. Appending to file." % profile_py_filename
            profile_py += '\n\n' + PROFILE_HEADER

        profile_py += header(
            'EXPORTED ON %s' % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ) + '\n'

        output_stream = StringIO.StringIO()

    print_types(types, output_stream)
    print >> output_stream, "\n"
    print_messages(messages, output_stream)

    if profile_py_filename:
        profile_py += output_stream.getvalue()
        open(profile_py_filename, 'w').write(profile_py)


if __name__ == '__main__':
    main()
