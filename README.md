python-fitparse
===============

> :warning: **NOTE:** *I have **limited to no time** to work on this package
> these days!*
> 
> I am looking for a maintainer to help with issues and updating/releasing the package.
> Please reach out via email at <david@dtcooper.com> if you have interest in helping.
>
> If you're having trouble using this package for whatever reason, might we suggest using
> an alternative library: [fitdecode](https://github.com/polyvertex/fitdecode) by
> [polyvertex](https://github.com/polyvertex).
>
> Cheers,
>
> David

Here's a Python library to parse ANT/Garmin `.FIT` files.
[![Build Status](https://github.com/dtcooper/python-fitparse/workflows/test/badge.svg)](https://github.com/dtcooper/python-fitparse/actions?query=workflow%3Atest)


Install from [![PyPI](https://img.shields.io/pypi/v/fitparse.svg)](https://pypi.python.org/pypi/fitparse/):
```
pip install fitparse
```

FIT files
------------
- FIT files contain data stored in a binary file format.
- The FIT (Flexible and Interoperable Data Transfer) file protocol is specified
  by [ANT](http://www.thisisant.com/).
- The SDK, code examples, and detailed documentation can be found in the
  [ANT FIT SDK](http://www.thisisant.com/resources/fit).


Usage
-----
A simple example of printing records from a fit file:

```python
import fitparse

# Load the FIT file
fitfile = fitparse.FitFile("my_activity.fit")

# Iterate over all messages of type "record"
# (other types include "device_info", "file_creator", "event", etc)
for record in fitfile.get_messages("record"):

    # Records can contain multiple pieces of data (ex: timestamp, latitude, longitude, etc)
    for data in record:

        # Print the name and value of the data (and the units if it has any)
        if data.units:
            print(" * {}: {} ({})".format(data.name, data.value, data.units))
        else:
            print(" * {}: {}".format(data.name, data.value))

    print("---")
```

The library also provides a `fitdump` script for command line usage:
```
$ fitdump --help
usage: fitdump [-h] [-v] [-o OUTPUT] [-t {readable,json}] [-n NAME] [--ignore-crc] FITFILE

Dump .FIT files to various formats

positional arguments:
  FITFILE               Input .FIT file (Use - for stdin)

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose
  -o OUTPUT, --output OUTPUT
                        File to output data into (defaults to stdout)
  -t {readable,json}, --type {readable,json}
                        File type to output. (DEFAULT: readable)
  -n NAME, --name NAME  Message name (or number) to filter
  --ignore-crc          Some devices can write invalid crc's, ignore these.
```

See the documentation for more: http://dtcooper.github.io/python-fitparse


Major Changes From Original Version
-----------------------------------

After a few years of laying dormant we are back to active development!
The old version is archived as
[`v1-archive`](https://github.com/dtcooper/python-fitparse/releases/tag/v1-archive).

  * New, hopefully cleaner public API with a clear division between accessible
    and internal parts. (Still unstable and partially complete.)

  * Proper documentation!
    [Available here](https://dtcooper.github.io/python-fitparse/).

  * Unit tests and example programs.

  * **(WIP)** Command line tools (eg a `.FIT` to `.CSV` converter).

  * Component fields and compressed timestamp headers now supported and not
    just an afterthought. Closes issues #6 and #7.

  * FIT file parsing is generic enough to support all types. Going to have
    specific `FitFile` subclasses for more popular file types like activities.

  * **(WIP)** Converting field types to normalized values (for example,
    `bool`, `date_time`, etc) done in a consistent way, that's easy to
    customize by subclassing the converter class. I'm going to use something
    like the Django form-style `convert_<field name>` idiom on this class.

  * The FIT profile is its own complete python module, rather than using
    `profile.def`.

    * Bonus! The profile generation script is _less_ ugly (but still an
      atrocity) and supports every
      [ANT FIT SDK](http://www.thisisant.com/resources/fit) from version 1.00
      up to 5.10.

  * A working `setup.py` module. Closes issue #2, finally! I'll upload the
    package to [PyPI](http://pypi.python.org/) when it's done.

  * Support for parsing one record at a time. This can be done using
    `<FitFile>.parse_one()` for now, but I'm not sure of the exact
    implementation yet.


Updating to new FIT SDK versions
--------------------------------
- Download the latest [ANT FIT SDK](http://www.thisisant.com/resources/fit).
- Update the profile:
```
python3 scripts/generate_profile.py /path/to/fit_sdk.zip fitparse/profile.py
```


License
-------

This project is licensed under the MIT License - see the [`LICENSE`](LICENSE)
file for details.
