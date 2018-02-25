python-fitparse
===============

Here's a Python library to parse ANT/Garmin `.FIT` files.

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
  
Major Changes From Original Version
-----------------------------------

After a few years of laying dormant we are back to active development!
The old version is archived as
[`v1-archive`](https://github.com/dtcooper/python-fitparse/releases/tag/v1-archive).

  * New, hopefully cleaner public API with a clear division between accessible
    and internal parts. (Still unstable and partially complete.)

  * Proper documentation!
    [Available here](http://dtcooper.github.com/python-fitparse/).

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

Donations
---------

You can donate to Bitcoin address: `1GAYJEWCGDaY1FbSfdD8W9Qzevu14UJTX6`


License
-------

This project is licensed under the MIT License - see the [`LICENSE`](LICENSE)
file for details.
