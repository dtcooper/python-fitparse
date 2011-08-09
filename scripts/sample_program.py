#!/usr/bin/env python
#
# Copyright (c) 2011, David Cooper <dave@kupesoft.com>
# All rights reserved.
#
# Dedicated to Kate Lacey
#
# Permission to use, copy, modify, and/or distribute this software
# for any purpose with or without fee is hereby granted, provided
# that the above copyright notice, the above dedication, and this
# permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHORS DISCLAIMS ALL
# WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL
# THE AUTHORS BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR
# CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
# LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
# NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
# CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

import os
import sys

# Add folder to search path

PROJECT_PATH = os.path.realpath(os.path.join(sys.path[0], '..'))
sys.path.append(PROJECT_PATH)

from fitparse.activity import Activity

quiet = 'quiet' in sys.argv or '-q' in sys.argv
filenames = None

if len(sys.argv) >= 2:
    filenames = [f for f in sys.argv[1:] if os.path.exists(f)]

if not filenames:
    filenames = [os.path.join(PROJECT_PATH, 'tests', 'data', 'sample-activity.fit')]

def print_records(activity):
    for rec in activity.records:
        print ("----- #%d: %s (%d entries) " % (rec.num, rec.type.name, len(rec.fields))).ljust(60, '-')
        for field in rec.fields:
            print "%s [%s]: %s " % (field.name, field.type.name, field.data)
    print

for f in filenames:
    if quiet:
        print f
    else:
        print ('##### %s ' % f).ljust(60, '#')

    a = Activity(f)
    a.parse()

    if not quiet:
        print_records(a)
