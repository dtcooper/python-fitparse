.. _api:

The ``fitparse`` API Documentation
==================================

.. module:: fitparse


The ``FitFile`` Object
----------------------

.. class:: FitFile(fileish, check_crc=True, data_processor=None)

    Interface for reading a ``.FIT`` file.

    Provided a ``.FIT`` file `fileish`, this is the main interface to parsing
    a ``.FIT`` file and reading its data.

    :param fileish: A file path, file-like object, or a string of bytes
        representing FIT data to be read.

        .. note:: Usage Notes

            All of the following work with the `fileish` parameter::

                # Specifying a file path
                fitfile = FitFile('/path.to/fitfile.fit')

                # Providing a file-like object
                file_obj = open('/path.to/fitfile.fit', 'rb')
                fitfile = FitFile(file_obj)

                # Providing a raw string of bytes
                file_obj = open('/path.to/fitfile.fit', 'rb')
                raw_fit_data = file_obj.read()
                fitfile = FitFile(raw_fit_data)

    :param check_crc: Set to ``False`` if to disable CRC validation while
        reading the current ``.FIT`` file.

    :param data_processor: Use this parameter to specify an alternate data
        processor object to use. If one is not provided, an instance of
        :class:`FitFileDataProcessor` will be used.

    :raises: Creating a :class:`FitFile` may raise a :exc:`FitParseError`
        exception. See the :ref:`note on exceptions <exception_warning>`.


    .. method:: get_messages(name=None, with_definitions=False, as_dict=False)

        TODO: document and implement


    .. method:: parse()

        Parse the underlying FIT data completely.

        :raises: May raise a :exc:`FitParseError` exception.

        .. _exception_warning:
        .. warning:: Note on Exceptions While Parsing a ``.FIT`` File

            In general, any operation on a that :class:`FitFile` that results in
            parsing the underlying FIT data may throw a :exc:`FitParseError`
            exception when invalid data is encountered.

            One way to catch these before you start reading going through the
            messages contained in a :class:`FitFile` is to call
            :meth:`parse()` immediately after creating a
            :class:`FitFile` object. For example::


                import sys
                from fitparse import FitFile, FitParseError

                try:
                    fitfile = FitFile('/path.to/fitfile.fit')
                    fitfile.parse()
                except FitParseError as e:
                    print "Error while parsing .FIT file: %s" % e
                    sys.exit(1)


            Any file related IO exceptions caught during a `read()` or `close()`
            operation will be raised as usual.


    .. attribute:: messages

        The complete `list` of :class:`DataMessage` record objects that are
        contained in this :class:`FitFile`. This list is provided as a
        convenience attribute that wraps :meth:`get_messages()`. It is
        functionally equivalent to::

            class FitFile(object):
                # ...

                @property
                def messages(self):
                    return list(self.get_messages())

        :raises: Reading this property may raise a :exc:`FitParseError`
            exception. See the :ref:`note on exceptions <exception_warning>`.


    .. attribute:: profile_version

        The profile version of the FIT data read (see ANT FIT SDK for)

    .. attribute:: protocol_version

        The protocol version of the FIT data read (see ANT FIT SDK)


Record Objects
--------------


Common Used Record Objects
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. class:: DataMessage

    A list of `DataMessage` objects are returned by
    :meth:`FitFile.get_messages()` and :attr:`FitFile.messages`. These are not
    meant to be created directly.

    .. attribute:: fields

        A `list` of :class:`FieldData` objects representing the fields contained
        in this message.

    .. method:: get(field_name, as_dict=False)

        Returns a :class:`FieldData` for field `field_name` if it exists,
        otherwise `None`. If `as_dict` is set to `True`, returns a `dict`
        representation of the field (see :class:`FieldData.as_dict()`)

    .. method:: get_value(field_name)

        Returns the value of `field_name` if it exists, otherwise `None`

    .. method:: get_values()

        Return a `dict` mapping of field names to their values. For example::

            >> data_message.get_values()
            {
                'altitude': 24.6,
                'cadence': 97,
                'distance': 81.97,
                'grade': None,
                'heart_rate': 153,
                'position_lat': None,
                'position_long': None,
                'power': None,
                'resistance': None,
                'speed': 7.792,
                'temperature': 20,
                'time_from_course': None,
                'timestamp': datetime.datetime(2011, 11, 6, 13, 41, 50)
            }


    .. method:: as_dict()

        TODO: document me

    .. attribute:: name

        The name of this `DataMessage`, as defined by its :attr:`def_mesg`.

    .. attribute:: def_mesg

        .. note::

            Generally this attribute is for access to FIT internals only

        The :class:`DefinitionMessage` associated with this `DataMessage`.
        These are encountered while parsing FIT data and are declared to define
        the data contained in a `DataMessage.

    .. attribute:: mesg_num

        The message number of this `DataMessage`, as defined by its
        :attr:`def_mesg`.

    .. attribute:: mesg_type

        The :class:`MessageType` associated with the :attr:`mesg_num` for this
        `DataMessage`. If no associated message type is defined in the
        :ref:`SDK profile <profile>`, then this is set to `None`.

        TODO: Document SDK profile and update link

