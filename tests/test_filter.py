import numpy as np
import pytest

from pyaerocom.config import ALL_REGION_NAME
from pyaerocom.filter import Filter


# TODO: use mark.parametrize for first 2 test functions and call test_Filter
def test_Filter_init():
    assert Filter("EUROPE").name == "EUROPE-wMOUNTAINS"
    assert Filter("noMOUNTAINS-OCN-NAMERICA").name == "NAMERICA-noMOUNTAINS-OCN"


def test_filter_attributes():
    f = Filter(f"{ALL_REGION_NAME}-noMOUNTAINS-LAND")
    assert f.land_ocn == "LAND"
    assert f.region_name == ALL_REGION_NAME
    assert f.name == f"{ALL_REGION_NAME}-noMOUNTAINS-LAND"
    assert not f.region.is_htap()


@pytest.mark.parametrize(
    "filter_name, mean",
    [
        ("EUROPE-noMOUNTAINS-LAND", 0.16616775),
        ("EUROPE-noMOUNTAINS-OCN", 0.1314668),
        ("EUROPE", 0.13605888),
    ],
)
def test_filter_griddeddata(data_tm5, filter_name, mean):

    # use copy so that this fixture can be used elsewhere without being c
    # changed by this method globally
    model = data_tm5.copy()

    f = Filter(filter_name)  # europe only land

    subset = f.apply(model)
    assert np.nanmean(subset.cube.data) == pytest.approx(mean)


@pytest.mark.parametrize(
    "filter_name,num_sites", [(f"{ALL_REGION_NAME}-wMOUNTAINS", 22), ("OCN", 8), ("EUROPE", 7)]
)
def test_filter_ungriddeddata(aeronetsunv3lev2_subset, filter_name, num_sites):

    obs_data = aeronetsunv3lev2_subset

    f = Filter(filter_name)
    num = len(f.apply(obs_data).unique_station_names)
    assert num == num_sites


@pytest.mark.skip(reason=("Need to storee colocateddata object in tmp_dir and provide as fixture"))
def test_filter_colocateddata():
    pass


# =============================================================================
#     data_coloc = pya.colocation.colocate_gridded_gridded(model,
#                                                          sat,
#                                                          ts_type='monthly',
#                                                          filter_name='WORLD-noMOUNTAINS-OCN')
#
#     assert data_coloc.data.sum().values - 111340.31777193633 < 0.001
# =============================================================================
