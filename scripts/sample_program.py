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

filename = None

if len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
    filename = sys.argv[1]

if not filename:
    filename = os.path.join(PROJECT_PATH, 'tests', 'data', 'sample-activity.fit')

a = Activity(filename)
a.parse()

def print_records(records):
    for rec in records:
        print ("----- #%d: %s (%d entries) " % (rec.num, rec.type.name, len(rec.fields))).ljust(60, '-')
        for field in rec.fields:
            print "%s [%s]: %s " % (field.name, field.type.name, field.data)

if 'quiet' not in sys.argv:
    if '-a' not in sys.argv:
        print_records(r for r in a.records if r.definition.type.num == 20)
    else:
        print_records(a.records)
