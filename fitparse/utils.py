import re


class FitParseError(ValueError):
    pass

class FitEOFError(FitParseError):
    pass

class FitCRCError(FitParseError):
    pass

class FitHeaderError(FitParseError):
    pass


CRC_TABLE = (
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
)


def calc_crc(byte_arr, crc=0):
    for byte in bytearray(byte_arr):
        # Taken verbatim from FIT SDK docs
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[byte & 0xF]

        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


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
