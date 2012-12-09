python-fitparse
===============

Important Note
--------------

This version of the library is **deprecated** and it is currently being
rewritten on the ng branch.

For now, the master branch can still be considered stable. Updates to come.


About
-----

Here's a Python library to parse ANT/Garmin .FIT files. These are files
produced by several newer Garmin cycling computers, notably the Garmin Edge
500 and Edge 800.

The FIT (Flexible and Interoperable Data Transfer) file protocol is specified
by ANT (<http://www.thisisant.com/>) and an SDK is available for download at
<http://www.thisisant.com/pages/products/fit-sdk>.

I'm currently using version 1.1 of the SDK to develop this library
(FitSDK1_2.zip).


Sample Usage
------------

The package is by no means mature, but here's one sample usage for now.

    #!/usr/bin/env python

    # Sample usage of python-fitparse to parse an activity and
    # print its data records.


    from fitparse import Activity

    activity = Activity("/path.to/activity-file.fit")
    activity.parse()

    # Records of type 'record' (I know, confusing) are the entries in an
    # activity file that represent actual data points in your workout.
    records = activity.get_records_by_type('record')
    current_record_number = 0

    for record in records:

        # Print record number
        current_record_number += 1
        print (" Record #%d " % current_record_number).center(40, '-')

        # Get the list of valid fields on this record
        valid_field_names = record.get_valid_field_names()

        for field_name in valid_field_names:
            # Get the data and units for the field
            field_data = record.get_data(field_name)
            field_units = record.get_units(field_name)

            # Print what we've got!
            if field_units:
                print " * %s: %s %s" % (field_name, field_data, field_units)
            else:
                print " * %s: %s" % (field_name, field_data)

        print


License
-------

    Copyright (c) 2011-2012, David Cooper <dave@kupesoft.com>
    All rights reserved.

    Dedicated to Kate Lacey

    Permission to use, copy, modify, and/or distribute this software
    for any purpose with or without fee is hereby granted, provided
    that the above copyright notice, the above dedication, and this
    permission notice appear in all copies.

    THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL
    WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED
    WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL
    THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR
    CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
    LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
    NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
    CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

