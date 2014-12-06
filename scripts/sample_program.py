#!/usr/bin/env python

import os
import sys

# Add folder to search path

PROJECT_PATH = os.path.realpath(os.path.join(sys.path[0], '..'))
sys.path.append(PROJECT_PATH)

from fitparse import Activity

quiet = 'quiet' in sys.argv or '-q' in sys.argv
filenames = None

if len(sys.argv) >= 2:
    filenames = [f for f in sys.argv[1:] if os.path.exists(f)]

if not filenames:
    filenames = [os.path.join(PROJECT_PATH, 'tests', 'data', 'sample-activity.fit')]


def print_record(rec, ):
    global record_number
    record_number += 1
    print ("-- %d. #%d: %s (%d entries) " % (record_number, rec.num, rec.type.name, len(rec.fields))).ljust(60, '-')
    for field in rec.fields:
        to_print = "%s [%s]: %s" % (field.name, field.type.name, field.data)
        if field.data is not None and field.units:
            to_print += " [%s]" % field.units
        print to_print
    print

for f in filenames:
    if quiet:
        print f
    else:
        print ('##### %s ' % f).ljust(60, '#')

    print_hook_func = None
    if not quiet:
        print_hook_func = print_record

    record_number = 0
    a = Activity(f)
    a.parse(hook_func=print_hook_func)
