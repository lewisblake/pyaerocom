#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General helper methods for the pyaerocom library.
"""
from pyaerocom import const
import re
from pyaerocom.time_config import (PANDAS_FREQ_TO_TS_TYPE, 
                                   TS_TYPE_TO_PANDAS_FREQ)
from pyaerocom.exceptions import TemporalResolutionError

class TsType(object):
    VALID = const.GRID_IO.TS_TYPES
    FROM_PANDAS = PANDAS_FREQ_TO_TS_TYPE
    TO_PANDAS = TS_TYPE_TO_PANDAS_FREQ
    
    TS_MAX_VALS = {'hourly' : 24,
                   'daily'  : 7,
                   'weekly' : 4,
                   'monthly': 12}
    
    def __init__(self, val):
        self._mulfac = 1.0
        self._val = None
        
        self.val = val
    
    
    @property
    def mulfac(self):
        """Multiplication factor of frequency"""
        return self._mulfac
    
    @property
    def base(self):
        """Base string (without multiplication factor, cf :attr:`mulfac`)"""
        return self._val
    
    @property
    def name(self):
        """Name of ts_type (Wrapper for :attr:`val`)"""
        return self.val
    
    @property
    def val(self):
        """Value of frequency (string type), e.g. 3daily"""
        if self._mulfac != 1:
            return '{}{}'.format(self._mulfac, self._val)
        return self._val
    
    @val.setter
    def val(self, val):
        ival=1
        if val[-1].isdigit():
            raise TemporalResolutionError('Invalid input for TsType: {}'
                                          .format(val))
        elif val[0].isdigit():
            ivalstr = re.findall('\d+', val)[0]
            val = val.split(ivalstr)[-1]
            ival = int(ivalstr)
        if not val in self.VALID:
            try:
                val = self._from_pandas(val)
            except TemporalResolutionError:
                raise TemporalResolutionError('Invalid input. Need any valid '
                                              'ts_type: {}'
                                              .format(self.VALID))
        if val in self.TS_MAX_VALS and ival != 1:
            if ival > self.TS_MAX_VALS[val]:
                raise TemporalResolutionError('Invalid input for ts_type {}{}. '
                                              'Interval factor {} exceeds '
                                              'maximum allowed for {}, which '
                                              'is: {}'
                                              .format(ival, val, ival, val, 
                                                      self.TS_MAX_VALS[val]))
        self._val = val
        self._mulfac = ival
        
    @staticmethod
    def infer(self, datetime_index):
        """Infer resolution based on input datateime_index
        
        Uses :func:`pandas.infer_freq` to infer frequency
        """
        raise NotImplementedError
    
    @staticmethod
    def valid(val):
        try:
            TsType(val)
            return True
        except TemporalResolutionError:
            return False
        
    @property
    def next_lower(self):
        """Next lower resolution code"""
        idx = self.VALID.index(self._val)
        if idx == len(self.VALID) - 1:
            raise IndexError('No lower resolution available than {}'.format(self))
        return TsType(self.VALID[idx+1])
    
    @property
    def next_higher(self):
        """Next lower resolution code"""
        
        idx = self.VALID.index(self._val)
        if idx == 0:
            raise IndexError('No lower resolution available than {}'.format(self))
        return TsType(self.VALID[idx-1])
    
    def to_pandas(self):
        """Convert ts_type to pandas frequency string"""
        freq = self.TO_PANDAS[self._val]
        if self._mulfac == 1:
            return freq
        return '{}{}'.format(self._mulfac, freq)
        
    def _from_pandas(self, val):
        if not val in self.FROM_PANDAS:
            raise TemporalResolutionError('Invalid input: {}, need pandas '
                                          'frequency string'
                                          .format(val))
        return self.FROM_PANDAS[val]
    
    def __lt__(self, other):
        if self.val == other.val:
            return False
        
        idx_this = self.VALID.index(self._val)
        idx_other = self.VALID.index(other._val)
        if not idx_this == idx_other: #they have a different freq string
            return idx_this > idx_other
        #they have the same frequency string but different _mulfac attributes
        return self._mulfac > other._mulfac
    
    def __le__(self, other):
        return True if (self.__eq__(other) or self.__lt__(other)) else False
    
    def __eq__(self, other):
        return other.val == self.val
    
    def __call__(self):
        return self.val
    
    def __str__(self):
        return self.val
    
    def __repr__(self):
        return self.val
    
def sort_ts_types(ts_types):
    """Sort a list of ts_types
    
    Parameters
    ----------
    ts_types : list
        list of strings (or instance of :class:`TsType`) to be sorted
    
    Returns
    -------
    list
        list of strings with sorted frequencies
        
    Raises 
    ------
    TemporalResolutionError
        if one of the input ts_types is not supported
    """
    freqs_sorted = []
    for ts_type in ts_types:
        if isinstance(ts_type, str):
            ts_type = TsType(ts_type)
        if len(freqs_sorted) == 0:
            freqs_sorted.append(ts_type)
        else: 
            insert = False
            for i, tt in enumerate(freqs_sorted):
                if tt < ts_type:
                    insert=True
                    break
            if insert:
                freqs_sorted.insert(i, ts_type)
            else:
                freqs_sorted.append(ts_type)
            print(x for x in freqs_sorted)
    return [str(tt) for tt in freqs_sorted]
                
if __name__=="__main__":

    
    daily = TsType('daily')
    monthly = TsType('monthly')
    
    print('Monthly < daily:', monthly < daily)
    print('Monthly == daily:', monthly == daily)
    print('Daily == daily:', daily==daily)
    print('Monthly <= daily:', monthly <= daily)
    print('daily >= monthly:', daily   >= monthly)
    print('daily > monthly:', daily > monthly)
    print('Monthly >= daily:', monthly >= daily)
    
    hourly = TsType('hourly')
    hourly5 = TsType('5hourly')

    print(hourly)
    print(hourly5)
    
    print('hourly == 5hourly:', hourly==hourly5)
    print('hourly > 5hourly:', hourly>hourly5)
    
    print(TsType('yearly').next_higher)
    
    
    hourly = TsType('hourly')
    
    daily = hourly.next_lower

    print(hourly.next_lower)
    
    unsorted = ['monthly', 'hourly', '5minutely', '3daily', 'daily']
    
    sort = sort_ts_types(unsorted)
    
    print(sort)
# =============================================================================
#     
#     class Num(object):
#         def __init__(self, val):
#             self.val = val
#             
#         def __lt__(self, other):
#             print('Other is smaller than this')
#             return self.val < other.val
#         
#     print(Num(3) < Num(5))
# =============================================================================
