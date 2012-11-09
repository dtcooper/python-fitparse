from fitparse.exceptions import FitParseError
from fitparse.base import FitFile


class Activity(FitFile):
    def parse(self, *args, **kwargs):
        return_value = super(Activity, self).parse(*args, **kwargs)
        if self.records[0].get_data('type') != 'activity':
            raise FitParseError("File parsed is not an activity file.")
        return return_value
