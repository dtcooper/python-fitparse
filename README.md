python-fitparse
===============

Welcome to the rewrite for the next generation (ng) of python-fitparse.

Here's a preview of what's to come. Any and all feedback is welcome.

**WARNING:** This is a WIP considered *HIGHLY* unstable. You want to use the
master branch for now.

Major Changes
-------------

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


License
-------

This software is offered under a *slightly* modified ISC-style license.


    Copyright (c) 2011-2013, David Cooper <dave@kupesoft.com>
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
