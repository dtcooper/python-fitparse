import contextlib
import datetime
from fitparse.utils import scrub_method_name


class FitFileDataProcessor(object):
    # TODO: Document API
    # Functions that will be called to do the processing:
    #def run_type_processor(field_data)
    #def run_field_processor(field_data)
    #def run_unit_processor(field_data)
    #def run_message_processor(data_message)

    # By default, the above functions call these functions if they exist:
    #def process_type_<type_name> (field_data)
    #def process_field_<field_name> (field_data) -- can be unknown_DD but NOT recommended
    #def process_units_<unit_name> (field_data)
    #def process_message_<mesg_name / mesg_type_num> (data_message)

    def run_type_processor(self, field_data):
        self._run_processor(scrub_method_name('process_type_%s' % field_data.type.name), field_data)

    def run_field_processor(self, field_data):
        self._run_processor(scrub_method_name('process_field_%s' % field_data.name), field_data)

    def run_unit_processor(self, field_data):
        if field_data.units:
            self._run_processor(scrub_method_name('process_units_%s' % field_data.units), field_data)

    def run_message_processor(self, data_message):
        self._run_processor(scrub_method_name('process_message_%s' % data_message.def_mesg.name), data_message)

    def _run_processor(self, processor_name, data):
        with contextlib.suppress(AttributeError):
            getattr(self, processor_name)(data)

    def process_type_bool(self, field_data):
        if field_data.value is not None:
            field_data.value = bool(field_data.value)

    def process_type_date_time(self, field_data):
        value = field_data.value
        if value is not None and value >= 0x10000000:
            field_data.value = datetime.datetime.utcfromtimestamp(631065600 + value)
            field_data.units = None  # Units were 's', set to None

    def process_type_local_date_time(self, field_data):
        if field_data.value is not None:
            field_data.value = datetime.datetime.fromtimestamp(631065600 + field_data.value)
            field_data.units = None

    def process_type_localtime_into_day(self, field_data):
        if field_data.value is not None:
            m, s = divmod(field_data.value, 60)
            h, m = divmod(m, 60)
            field_data.value = datetime.time(h, m, s)
            field_data.units = None


class StandardUnitsDataProcessor(FitFileDataProcessor):
    def run_field_processor(self, field_data):
        """
        Convert all '*_speed' fields using 'process_field_speed'
        All other units will use the default method.
        """
        if field_data.name.endswith("_speed"):
            self.process_field_speed(field_data)
        else:
            super().run_field_processor(field_data)

    def process_field_distance(self, field_data):
        if field_data.value is not None:
            field_data.value /= 1000.0
        field_data.units = 'km'

    def process_field_speed(self, field_data):
        if field_data.value is not None:
            field_data.value *= 60.0 * 60.0 / 1000.0
        field_data.units = 'km/h'

    def process_units_semicircles(self, field_data):
        if field_data.value is not None:
            field_data.value *= 180.0 / (2 ** 31)
        field_data.units = 'deg'
