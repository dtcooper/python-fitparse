===========================
python-fitparse Documention
===========================

.. toctree::
   :maxdepth: 2

   api


Introduction
============

The :mod:`fitparse` module is a Python library for parsing
`ANT <http://www.thisisant.com>`_/`Garmin <http://www.garmin.com>`_ ``.FIT``
files.

The FIT (Flexible and Interoperable Data Transfer) file protocol is specified
by `ANT <http://www.thisisant.com>`_ in its FIT SDK. It's a common file format
used internally on embedded fitness computers, for example on the Edge and
Forerunner series of `Garmin <http://www.garmin.com>`_ products.


Quickstart Guide
----------------

TODO


Installation
------------

Using ``pip``
~~~~~~~~~~~~~

The easiest way to grab :mod:`fitparse` is using ``pip``,

::

    $ pip install python-fitparse


From github
~~~~~~~~~~~

Navigate to `dtcooper/python-fitparse <https://github.com/dtcooper/python-fitparse>`_
on github and clone the latest version::

    $ git clone git@github.com:dtcooper/python-fitparse.git
    $ cd python-fitparse
    $ python setup.py install


Requirements
~~~~~~~~~~~~

The following are required to install :mod:`fitparse`,

* `Python <http://www.python.org/>`_ 2.5 and above (Python 3 is currently not
  supported)

* The `argparse <https://code.google.com/p/argparse/>`_ is required for the
  :command:`fitdump` command, but it is included in the Python standard library
  as of version 2.7. Using ``pip`` to install the package will install this if
  needed.


API Documentation
-----------------

If you are looking for information on a specific function, class or method,
this part of the documentation is for you.

.. toctree::
   :maxdepth: 2

   api



Usage Examples
--------------

Here's a simple program to print all the record fields in an activity file::

    from fitparse import FitFile


    fitfile = FitFile('/home/dave/garmin-activities/2012-12-19-16-14-54.fit')

    # Get all data messages that are of type record
    for record in fitfile.get_messages('record'):

        # Go through all the data entries in this record
        for record_data in record:

            # Print the records name and value (and units if it has any)
            if record_data.units:
                print " * %s: %s %s" % (
                    record_data.name, record_data.value, record_data.units,
                )
            else:
                print " * %s: %s" % (record_data.name, record_data.value)
        print


License
-------


.. include:: ../LICENSE
   :literal:
