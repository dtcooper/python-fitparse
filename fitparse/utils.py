import datetime
import io
import re
from collections import Iterable


class FitParseError(ValueError):
    pass

class FitEOFError(FitParseError):
    pass

class FitCRCError(FitParseError):
    pass

class FitHeaderError(FitParseError):
    pass


UTC_REFERENCE = datetime.datetime(1989, 12, 31)  # timestamp for UTC 00:00 Dec 31 1989
METHOD_NAME_SCRUBBER = re.compile(r'\W|^(?=\d)')
UNIT_NAME_TO_FUNC_REPLACEMENTS = (
    ('/', ' per '),
    ('%', 'percent'),
    ('*', ' times '),
)


def fit_to_datetime(sec):
    """Convert FIT seconds to datetime."""
    return UTC_REFERENCE + datetime.timedelta(seconds=sec)


def fit_from_datetime(dt):
    """Convert datetime to FIT seconds."""
    return int((dt - UTC_REFERENCE).total_seconds())


def fit_semicircles_to_deg(sc):
    """Convert FIT semicircles to deg (for the GPS lat, long)."""
    return sc * 180.0 / (2 ** 31)


def fit_deg_to_semicircles(deg):
    """Convert deg to FIT semicircles (for the GPS lat, long)."""
    return int(deg / 180.0 * (2 ** 31))


def scrub_method_name(method_name, convert_units=False):
    if convert_units:
        for replace_from, replace_to in UNIT_NAME_TO_FUNC_REPLACEMENTS:
            method_name = method_name.replace(
                replace_from, '%s' % replace_to,
            )
    return METHOD_NAME_SCRUBBER.sub('_', method_name)


def fileish_open(fileish, mode):
    """
    Convert file-ish object to BytesIO like object.
    :param fileish: the file-ihs object (str, BytesIO, bytes, file contents)
    :param str mode: mode for the open function.
    :rtype: BytesIO
    """
    if mode is not None and any(m in mode for m in ['+', 'w', 'a', 'x']):
        attr = 'write'
    else:
        attr = 'read'
    if hasattr(fileish, attr) and hasattr(fileish, 'seek'):
        # BytesIO-like object
        return fileish
    elif isinstance(fileish, str):
        # Python2 - file path, file contents in the case of a TypeError
        # Python3 - file path
        try:
            return open(fileish, mode)
        except TypeError:
            return io.BytesIO(fileish)
    else:
        # Python 3 - file contents
        return io.BytesIO(fileish)


def is_iterable(obj):
    """Check, if the obj is iterable but not string or bytes.
    :rtype bool"""
    # Speed: do not use iter() although it's more robust, see also https://stackoverflow.com/questions/1952464/
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes))
