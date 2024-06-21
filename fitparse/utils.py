import io
import re
from collections.abc import Iterable

from pathlib import PurePath


class FitParseError(ValueError):
    pass

class FitEOFError(FitParseError):
    pass

class FitCRCError(FitParseError):
    pass

class FitHeaderError(FitParseError):
    pass


METHOD_NAME_SCRUBBER = re.compile(r'\W|^(?=\d)')
UNIT_NAME_TO_FUNC_REPLACEMENTS = (
    ('/', ' per '),
    ('%', 'percent'),
    ('*', ' times '),
)

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
        # file path
        return open(fileish, mode)

    # pathlib obj
    if isinstance(fileish, PurePath):
        return fileish.open(mode)

    # file contents
    return io.BytesIO(fileish)


def is_iterable(obj):
    """Check, if the obj is iterable but not string or bytes.
    :rtype bool"""
    # Speed: do not use iter() although it's more robust, see also https://stackoverflow.com/questions/1952464/
    return isinstance(obj, Iterable) and not isinstance(obj, (str, bytes))
