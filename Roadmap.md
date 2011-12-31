python-fitparse Road Map
========================

* For now, focus on Activity file types. I originally wrote it with maximum
flexibility in mind and now we have a situation where no one file type works
flawlessly. Then extend to other useful types, like Course, Workouts, and
Totals.

  * See FIT SDK docs for a list of types, and `Profile.xls`: messages worksheet.

* Parser to support "extremely odd types where field size != type size to a
byte" (see XXX comment in `fitparse/base.py:parse_definition_record()`).

* Rethink the whole `fitparse/record.py` Record framework. Do we really need to
use the NamedTuple pattern? What's wrong with just returning a list of dicts of
raw values.

  * Currently the parser takes up **way** too much CPU time and memory. I want to
  speed this up.

* `scripts/generate_profile.py` is a behemoth. Need to reconsider whether this
is the right way to do things. Especially if we're just going to focus on
Activity file types mostly.

* Generic way to hook into values after parsing, and fix them, for example
converting m/s to km/h and semi-circles to degrees longitude and latitude.
This could probably be done by sub-classing the parser and calling the child
classes fix-ups in some way.

* Review and update based on new FIT SDK v1.2 (FitSDK1_5.zip) 
at <http://www.thisisant.com/pages/ant/fit-license>
