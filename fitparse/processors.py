import datetime


class FitFileDataProcessor(object):
    # TODO: Document API
    #def process_type_<type_name> (field_data)
    #def process_field_<field_name> (field_data) -- can be unknown_DD but NOT recommended
    #def process_message_<mesg_name / mesg_type_num> (data_message)

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


class StandardUnitsDataProcessor(FitFileDataProcessor):
    # Example use case
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
