#!/usr/bin/env python

# Make classes available
from fitparse.base import FitFile, FitFileDecoder, UncachedFitFile, \
                          FitParseError, CacheMixin, DataProcessorMixin
from fitparse.records import DataMessage
from fitparse.processors import FitFileDataProcessor, StandardUnitsDataProcessor


__version__ = '1.2.0'
