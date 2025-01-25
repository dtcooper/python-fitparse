import datetime
from fitparse.utils import scrub_method_name, is_iterable

# Datetimes (uint32) represent seconds since this UTC_REFERENCE
UTC_REFERENCE = 631065600  # timestamp for UTC 00:00 Dec 31 1989


class FitFileDataProcessor:
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

    # Used to memoize scrubbed method names
    _scrubbed_method_names = {}

    def _scrub_method_name(self, method_name):
        """Scrubs a method name, returning result from local cache if available.

        This method wraps fitparse.utils.scrub_method_name and memoizes results,
        as scrubbing a method name is expensive.

        Args:
            method_name: Method name to scrub.

        Returns:
            Scrubbed method name.
        """
        if method_name not in self._scrubbed_method_names:
            self._scrubbed_method_names[method_name] = (
                scrub_method_name(method_name))

        return self._scrubbed_method_names[method_name]

    def run_type_processor(self, field_data):
        self._run_processor(self._scrub_method_name(
            'process_type_%s' % field_data.type.name), field_data)

    def run_field_processor(self, field_data):
        self._run_processor(self._scrub_method_name(
            'process_field_%s' % field_data.name), field_data)

    def run_unit_processor(self, field_data):
        if field_data.units:
            self._run_processor(self._scrub_method_name(
                'process_units_%s' % field_data.units), field_data)

    def run_message_processor(self, data_message):
        self._run_processor(self._scrub_method_name(
            'process_message_%s' % data_message.def_mesg.name), data_message)

    def _run_processor(self, processor_name, data):
        try:
            getattr(self, processor_name)(data)
        except AttributeError:
            pass

    def process_type_bool(self, field_data):
        if field_data.value is not None:
            field_data.value = bool(field_data.value)

    def process_type_date_time(self, field_data):
        value = field_data.value
        if value is not None and value >= 0x10000000:
            field_data.value = datetime.datetime.fromtimestamp(timestamp=(UTC_REFERENCE + value), tz=datetime.timezone.utc).replace(tzinfo=None)
            field_data.units = None  # Units were 's', set to None

    def process_type_local_date_time(self, field_data):
        if field_data.value is not None:
            # NOTE: This value was created on the device using it's local timezone.
            #       Unless we know that timezone, this value won't be correct. However, if we
            #       assume UTC, at least it'll be consistent.
            field_data.value = datetime.datetime.fromtimestamp(timestamp=(UTC_REFERENCE + field_data.value), tz=datetime.timezone.utc).replace(tzinfo=None)
            field_data.units = None

    def process_type_localtime_into_day(self, field_data):
        if field_data.value is not None:
            # NOTE: Values larger or equal to 86400 should not be possible.
            #       Additionally, if the value is exactly 86400, it will lead to an error when trying to
            #       create the time with datetime.time(24, 0 , 0).
            #
            #       E.g. Garmin does add "sleep_time": 86400 to its fit files,
            #       which causes an error if not properly handled.
            if field_data.value >= 86400:
                field_data.value = datetime.time.max
            else:
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
            factor = 60.0 * 60.0 / 1000.0

            # record.enhanced_speed field can be a tuple
            if is_iterable(field_data.value):
                field_data.value = tuple(x * factor for x in field_data.value)
            else:
                field_data.value *= factor
        field_data.units = 'km/h'

    def process_units_semicircles(self, field_data):
        if field_data.value is not None:
            field_data.value *= 180.0 / (2 ** 31)
        field_data.units = 'deg'
