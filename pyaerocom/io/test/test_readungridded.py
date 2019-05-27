#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jul  9 14:14:29 2018
"""
from pyaerocom.test.settings import TEST_RTOL, lustre_unavail
from pyaerocom.io import ReadUngridded

def test_supported():
    supported_datasets =ReadUngridded().supported_datasets
    assert len(supported_datasets) == 17
    assert supported_datasets == ['AeronetInvV3Lev2.daily',
                                 'AeronetInvV3Lev1.5.daily',
                                 'AeronetInvV2Lev2.daily',
                                 'AeronetInvV2Lev1.5.daily',
                                 'AeronetSDAV2Lev2.daily',
                                 'AeronetSDAV3Lev1.5.daily',
                                 'AeronetSDAV3Lev2.daily',
                                 'AeronetSunV2Lev2.daily',
                                 'AeronetSunV2Lev2.AP',
                                 'AeronetSunV3Lev1.5.daily',
                                 'AeronetSunV3Lev1.5.AP',
                                 'AeronetSunV3Lev2.daily',
                                 'AeronetSunV3Lev2.AP',
                                 'EARLINET',
                                 'EBASMC',
                                 'DMS_AMS_CVO',
                                 'GAWTADsubsetAasEtAl']


def test_basic_attributes():
    r = ReadUngridded()
    assert not r.ignore_cache
    assert r.datasets_to_read == ['AeronetSunV3Lev2.daily']
    assert type(r.get_reader()).__name__ == 'ReadAeronetSunV3'
    assert r.dataset_provides_variables() == ['od340aer', 'od440aer',
                                            'od500aer', 'od870aer',
                                            'ang4487aer', 'ang4487aer_calc',
                                            'od550aer']


if __name__=="__main__":

    test_supported()
    r = ReadUngridded()
    print(type(r.get_reader()).__name__)
    
# =============================================================================
#     d = make_dataset()
#     
#     for stat in d:
#         print(stat.station_name)
#         
#     
#     
# =============================================================================
