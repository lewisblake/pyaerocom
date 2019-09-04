#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Definitions and helpers related to time conversion
"""

from iris import coord_categorisation
from datetime import datetime
# The following import was removed and the information about available unit 
# strings was copied from the netCDF4 module directly here
# from netCDF4 import (microsec_units, millisec_units, sec_units, min_units,
#                     hr_units, day_units)
# from netCDF4._netCDF4 import _dateparse
microsec_units = ['microseconds', 'microsecond', 'microsec', 'microsecs']
millisec_units = ['milliseconds', 'millisecond', 'millisec', 'millisecs']
sec_units = ['second', 'seconds', 'sec', 'secs', 's']
min_units = ['minute', 'minutes', 'min', 'mins']
hr_units = ['hour', 'hours', 'hr', 'hrs', 'h']
day_units = ['day', 'days', 'd']

#
# Start of the gregorian calendar
# adapted from here: https://github.com/Unidata/cftime/blob/master/cftime/_cftime.pyx   
GREGORIAN_BASE = datetime(1582, 10, 15)

IRIS_AGGREGATORS = {'hourly'    :   coord_categorisation.add_hour,
                    'daily'     :   coord_categorisation.add_day_of_year,
                    'monthly'   :   coord_categorisation.add_month_number,
                    'yearly'    :   coord_categorisation.add_year} 

# some helper dictionaries for conversion of temporal resolution
TS_TYPE_TO_PANDAS_FREQ = {'hourly'  :   'H',
                          '3hourly' :   '3H',
                          'daily'   :   'D',
                          'weekly'  :   'W',
                          'monthly' :   'MS', #Month start !
                          'season'  :   'Q', 
                          'yearly'  :   'AS'}

PANDAS_RESAMPLE_OFFSETS = {'AS' : '6M',
                           'MS' : '14D'}

PANDAS_FREQ_TO_TS_TYPE = {v: k for k, v in TS_TYPE_TO_PANDAS_FREQ.items()}

# frequency strings 
TS_TYPE_TO_NUMPY_FREQ =  {'hourly'  :   'h',
                          '3hourly' :   '3h',
                          'daily'   :   'D',
                          'weekly'  :   'W',
                          'monthly' :   'M', #Month start !
                          'yearly'  :   'Y'}

# conversion of datetime-like objects for given temporal resolutions (can, e.g.
# be used in plotting methods)
TS_TYPE_DATETIME_CONV = {None       : '%d.%m.%Y', #Default
                         'hourly'   : '%d.%m.%Y',
                         '3hourly'  : '%d.%m.%Y',
                         'daily'    : '%d.%m.%Y',
                         'weekly'   : '%d.%m.%Y',
                         'monthly'  : '%b %Y',
                         'yearly'   : '%Y'}

TS_TYPE_SECS = {'hourly'  : 3600,
                '3hourly' : 10800,
                'daily'   : 86400,
                'weekly'  : 604800,
                'monthly' : 2592000, #counting 3 days per month (APPROX)
                'yearly'  : 31536000} #counting 365 days (APPROX)

XARR_TIME_GROUPERS = {'hourly'  : 'hour',
                      'daily'   : 'day',
                      'weekly'  : 'week',
                      'monthly' : 'month', 
                      'yearly'  : 'year'}