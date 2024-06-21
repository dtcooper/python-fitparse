#!/usr/bin/env python

# Tool for verifying sanity of units in Profile.xls / fitparse/profile.py

import os
import sys

import xlrd  # Dev requirement for parsing Excel spreadsheet

from fitparse.profile import MESSAGE_TYPES
from fitparse.utils import scrub_method_name


def do_profile_xls():
    workbook = xlrd.open_workbook(sys.argv[1])
    sheet = workbook.sheet_by_name('Messages')

    all_unit_values = []
    for unit_value in sheet.col_values(8):  # Extract unit column values
        unit_value = unit_value.strip()
        if unit_value:
            # Deal with comma separated components
            unit_values = [v.strip() for v in unit_value.split(',')]
            all_unit_values.extend(unit_values)

    print('In Profile.xls:')
    for unit_value in sorted(set(all_unit_values)):
        print(' * %s' % unit_value)


def do_fitparse_profile():
    unit_values = []
    for message_type in MESSAGE_TYPES.values():
        for field in message_type.fields.values():
            unit_values.append(field.units)
            if field.components:
                for component in field.components:
                    unit_values.append(component.units)
            if field.subfields:
                for subfield in field.subfields:
                    unit_values.append(subfield.units)
                    if subfield.components:
                        for component in subfield.components:
                            unit_values.append(component.units)

    unit_values = filter(None, unit_values)

    print('In fitparse/profile.py:')
    for unit_value in sorted(set(unit_values)):
        print(' * {} [{}]'.format(
            unit_value,
            scrub_method_name('process_units_%s' % unit_value, convert_units=True)
        ))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {os.path.basename(__file__)} Profile.xls")
        sys.exit(0)

    do_profile_xls()
    print()
    do_fitparse_profile()
