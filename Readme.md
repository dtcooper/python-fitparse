python-fitparse
===============

Important Note
--------------

This version (v1) of the library is no longer maintained and it has been
rewritten.

There will no fixes, no further releases, or support of code on this branch.
All bugs are now features!


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

This project is licensed under the MIT License - see the [`LICENSE`](LICENSE)
file for details.
