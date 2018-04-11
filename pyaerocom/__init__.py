def _init_supplemental():
    from pkg_resources import get_distribution
    from os.path import abspath, dirname
    return (get_distribution('pyaerocom').version, abspath(dirname(__file__)))

__version__, __dir__ = _init_supplemental()

from . import glob
from . import config
from . import mathutils
from . import test_files

from . import io
from . import plot

from .region import Region
from .modeldata import ModelData
from .obsdata import ObsData, ProfileData, StationData

