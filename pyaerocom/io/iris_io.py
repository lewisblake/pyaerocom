#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module containing helper functions related to iris I/O methods. These contain
reading of Cubes, and some methods to perform quality checks of the data, e.g.

1. checking and correction of time definition
2. number and length of dimension coordinates must match data array
3. Longitude definition from -180 to 180 (corrected if defined on 0 -> 360 intervall)

"""
import os
from datetime import datetime
from numpy import datetime64, asarray, arange
import cf_units

import iris
from iris.experimental.equalise_cubes import equalise_attributes

from pyaerocom import const, logger
from pyaerocom.exceptions import (NetcdfError, VariableDefinitionError,
                                  FileConventionError, 
                                  UnresolvableTimeDefinitionError)

from pyaerocom.helpers import cftime_to_datetime64
from pyaerocom.time_config import TS_TYPE_TO_PANDAS_FREQ
from pyaerocom.io.helpers import add_file_to_log
from pyaerocom.io.fileconventions import FileConventionRead

TSTR_TO_NP_DT = {"hourly"  :  "datetime64[h]",
                 "3hourly" :  "datetime64[3h]",
                 "daily"   :  "datetime64[D]",
                 "monthly" :  "datetime64[M]"}

TSTR_TO_NP_TD = {"hourly"  :  "timedelta64[h]",
                 "3hourly" :  "timedelta64[3h]",
                 "daily"   :  "timedelta64[D]",
                 "monthly" :  "timedelta64[M]"}


TSTR_TO_CF = {"hourly"  :  "hours",
              "3hourly" :  "hours",
              "daily"   :  "days",
              "monthly" :  "days"}

def _load_cubes_custom_multiproc(files, var_name=None, file_convention=None, 
                                 perform_checks=True, num_proc=None):
    """Like :func:`load_cubes_custom` but faster
    
    Uses multiprocessing module to distribute loading of multiple NetCDF files
    into iris cube.
    
    Parameters
    ----------
    file : list
        netcdf file
    var_name : str
        name of variable to read
    quality_check : bool
        if True, then a quality check of data is performed against the
        information provided in the filename
    file_convention : :obj:`FileConventionRead`, optional
        Aerocom file convention. If provided, then the data content (e.g. 
        dimension definitions) is tested against definition in file name
    perform_checks : bool
        if True, additional quality checks (and corrections) are (attempted to
        be) performed.
    num_proc : int
        number of jobs 
    
    Returns
    -------
    iris.cube.CubeList
        loaded data as Cube
    """    
    import multiprocessing
    from functools import partial
    if num_proc is None:
        num_proc = multiprocessing.cpu_count() * 2
    func = partial(load_cube_custom, 
                   var_name=var_name, file_convention=file_convention, 
                   perform_checks=perform_checks)
    p = multiprocessing.Pool(processes=num_proc)
    return p.map(func, files)

def load_cubes_custom(files, var_name=None, file_convention=None, 
                      perform_checks=True, **kwargs):
    """Load multiple NetCDF files into CubeList
    
    Parameters
    ----------
    files : list
        netcdf file
    var_name : str
        name of variable to read
    quality_check : bool
        if True, then a quality check of data is performed against the
        information provided in the filename
    file_convention : :obj:`FileConventionRead`, optional
        Aerocom file convention. If provided, then the data content (e.g. 
        dimension definitions) is tested against definition in file name
    perform_checks : bool
        if True, additional quality checks (and corrections) are (attempted to
        be) performed.
    **kwargs 
        additional keyword args that are parsed to 
        :func:`_load_cubes_custom_multiproc` in case number of input files 
        is larger than 4.
        
    Returns
    -------
    tuple
        2-element tuple containing:
            
            - CubeList, containing loaded cubes
            - list, list of filenames that were successfully loaded 
    """
    from pyaerocom import const
    if len(files) >= 4:
        try:
            cubes =  _load_cubes_custom_multiproc(files, var_name, 
                                                  file_convention, 
                                                  perform_checks,
                                                  **kwargs)
            # if this worked, all input files were successfully loaded and the 
            # function terminates, else, the retrieval is done file by file.
            return (cubes, files)
        except:
            pass
    cubes = []
    loaded_files = []
    for _file in files:
        try:
            cube = load_cube_custom(_file, var_name,
                                    file_convention=file_convention)
            cubes.append(cube)
            loaded_files.append(_file)
        except Exception as e:
            msg = ("Failed to load {} as Iris cube. Error: {}"
                   .format(_file, repr(e)))
            const.logger.warning(msg)
            
            if const.WRITE_FILEIO_ERR_LOG:
                add_file_to_log(_file, msg)
    return (cubes, loaded_files)

def load_cube_custom(file, var_name=None, file_convention=None, 
                     perform_checks=True):
    """Load netcdf file as iris.Cube
    
    Parameters
    ----------
    file : str
        netcdf file
    var_name : str
        name of variable to read
    quality_check : bool
        if True, then a quality check of data is performed against the
        information provided in the filename
    file_convention : :obj:`FileConventionRead`, optional
        Aerocom file convention. If provided, then the data content (e.g. 
        dimension definitions) is tested against definition in file name
    perform_checks : bool
        if True, additional quality checks (and corrections) are (attempted to
        be) performed.
    
    Returns
    -------
    iris.cube.Cube
        loaded data as Cube
    """
    cube_list = iris.load(file)
    
    _num = len(cube_list)
    if _num != 1:
        if _num == 0:
            raise NetcdfError('Data from file {} could not be loaded using iris'
                              .format(file))
        else:
            logger.warning('File {} contains more than one variable'
                           .format(file))
    cube = None
    if var_name is None:
        if not len(cube_list) == 1:
            vars_avail = [c.var_name for c in cube_list]
            raise NetcdfError('Could not load single cube from {}. Please '
                              'specify var_name. Input file contains the '
                              'following variables: {}'.format(file, 
                                                               vars_avail))
        cube = cube_list[0]
        var_name = cube.var_name
    else:
        for c in cube_list:
            if c.var_name == var_name:
                cube = c
                break
    if cube is None:
        raise NetcdfError('Variable {} not available in file {}'.format(var_name, 
                                                                        file))
    if perform_checks:
        try:
            cube = _check_var_unit_cube(cube)
        except VariableDefinitionError:
            pass
        
        grid_io = const.GRID_IO
        if grid_io.CHECK_TIME_FILENAME:
            cube = _check_correct_time_dim(cube, file,  file_convention)
        else:
            logger.warning("WARNING: Automatic check of time "
                           "array in netCDF files is deactivated. "
                           "This may cause problems in case "
                           "the time dimension is not CF conform.") 
        if grid_io.CHECK_DIM_COORDS:
            cube = check_dim_coords_cube(cube)
        
        try:
            if grid_io.DEL_TIME_BOUNDS:
                cube.coord("time").bounds = None
        except:
            logger.warning("Failed to access time coordinate in GriddedData")
            
        if grid_io.SHIFT_LONS:
            cube = check_and_regrid_lons_cube(cube)
    return cube

def check_and_regrid_lons_cube(cube):
    """Checks and corrects for if longitudes of :attr:`grid` are 0 -> 360
    
    Note
    ----
    This method checks if the maximum of the current longitudes array
    exceeds 180. Thus, it is not recommended to use this function after
    subsetting a cube, rather, it should be checked directly when the 
    file is loaded (cf. :func:`load_input`)
    
    Parameters
    ----------
    cube : iris.cube.Cube
        gridded data loaded as iris.Cube
        
    Returns
    -------
    bool
        True, if longitudes were on 0 -> 360 and have been rolled, else
        False
    """
    from pyaerocom import print_log
    try:
        if cube.coord("longitude").points.max() > 180:
            logger.info("Rolling longitudes to -180 -> 180 definition")
            cube = cube.intersection(longitude=(-180, 180))
    except Exception as e:
        print_log.warning('Failed to roll longitudes: {}'.format(repr(e)))
    return cube

def check_dim_coord_names_cube(cube):
    
    from pyaerocom import const
    coords = dict(lon = const.COORDINFO.lon,
                  lat = const.COORDINFO.lat,
                  time = const.COORDINFO.time)

    for coord in cube.dim_coords:
        cv, cs, cn = coord.var_name, coord.standard_name, coord.long_name
        c=None
        if cv in coords:
            c = coords[cv]
        elif cs in coords:
            c = coords[cs]
        elif cn in coords:
            c = coords[cn]
        if c is not None:
            var_name = c.var_name
            std_name = c.standard_name
            lng_name = c.long_name
            if not coord.var_name == var_name:
                const.logger.warning('Invalid var_name {} for coord {} '
                                        'in cube. Overwriting with {}'
                                        .format(coord.standard_name, 
                                                coord.var_name, 
                                                std_name))
                coord.var_name = var_name
            if not coord.standard_name == std_name:
                const.logger.warning('Invalid standard_name {} for coord {} '
                                        'in cube. Overwriting with {}'
                                        .format(coord.standard_name, 
                                                coord.var_name, 
                                                std_name))
                coord.standard_name = std_name
            if not coord.long_name == lng_name:
                const.logger.warning('Invalid long_name {} for coord {} in '
                                        'cube. Overwriting with {}'
                                        .format(coord.long_name, 
                                                coord.var_name, 
                                                lng_name))
                coord.long_name = lng_name
    return cube

def check_dim_coords_cube(cube):
    """Checks, and if necessary and applicable, updates coords names in Cube
    
    Parameters
    ----------
    cube : iris.cube.Cube
        input cube
    
    Returns
    -------
    iris.cube.Cube
        updated or unchanged cube
    """
    cube = check_dim_coord_names_cube(cube)
    return cube


def _check_var_unit_cube(cube):
    var = cube.var_name
    if not var in const.VARS:
        raise VariableDefinitionError('No such pyaerocom default variable: {}'
                                      .format(cube.var_name))
    
    u = cube.units
    if isinstance(u, str):
        u = cf_units.Unit(u)
    if str(const.VARS[var].units) == '1' and u.is_unknown():
        const.print_log.info('Overwriting unit {} in cube {} with value "1"'
                             .format(str(u), var))
        cube.units = cf_units.Unit('1')
    return cube

def check_time_coordOLD(cube, ts_type, year):
    """Method that checks the time coordinate of an iris Cube
    
    This method checks if the time dimension of a cube is accessible and 
    according to the standard (i.e. fully usable). It only checks, and does not
    correct. For the latter, please see :func:`correct_time_coord`.
    
    Parameters
    ----------
    cube : Cube
        cube containing data
    ts_type : str
        temporal resolution of data (e.g. "hourly", "daily"). This information
        is e.g. encrypted in the filename of a NetCDF file and may be 
        accessed using :class:`pyaerocom.io.FileConventionRead`
    year : int
        interger specifying year of observation, e.g. 2017
    
    Returns
    -------
    bool
        True, if time dimension is ok, False if not
    """
    
    ok = True
    test_idx = [0,1,2,7] #7, since last accessible index in a 3hourly dataset of one day is 7
    try:
        try:
            t = cube.coord("time")
        except:
            raise AttributeError("Cube does not contain time dimension")
        if not isinstance(t, iris.coords.DimCoord):
            raise AttributeError("Time is not a DimCoord instance")
        try:
            cftime_to_datetime64(0, cfunit=t.units)
        except:
            raise ValueError("Could not convert time unit string")
        tres_np = TSTR_TO_NP_TD[ts_type]
        conv = TSTR_TO_NP_DT[ts_type]
        base = datetime64("%s-01-01 00:00:00" %year).astype(conv)
        test_datenums = asarray(test_idx)
        ts_nominal = base + test_datenums.astype(tres_np)
        dts_nominal = ts_nominal[1:] - ts_nominal[:-1]
        ts_values = cftime_to_datetime64(t[test_idx].points, cfunit=t.units).astype(conv)
        dts_values = ts_values[1:] - ts_values[:-1]
        if not all(ts_values == ts_nominal):
            raise ValueError("Time match error, nominal dates for test array"
                             "%s (unit=%s): %s\nReceived values after "
                             "conversion: %s"
                             %(test_datenums, t.units.origin,
                               ts_nominal, ts_values))
        elif not all(dts_values == dts_nominal):
            raise ValueError("Time match error, time steps for test array"
                             "%s (unit=%s): %s\nReceived values after "
                             "conversion: %s"
                             %(test_datenums, t.units.origin,
                               dts_nominal, dts_values))
    except Exception as e:
        logger.warning("Invalid time dimension.\n"
                       "Error message: {}".format(repr(e)))
        ok = False
    return ok

def make_datetimeindex(ts_type, year):
    """Create pandas datetime index 
    
    Parameters
    ----------
    ts_type : str
        pyaerocom ts_type
    year : int
        year
        
    Returns
    -------
    pandas.DatetimeIndex
        index object
    """
    import pandas as pd
    start = datetime64("{}-01-01 00:00:00".format(year))
    stop = datetime64("{}-12-31 23:59:59".format(year))
    
    idx = pd.DatetimeIndex(start=start, end=stop, 
                           freq=TS_TYPE_TO_PANDAS_FREQ[ts_type])
    return idx



def _check_correct_time_dim(cube, file, file_convention=None):
    if file_convention is None:
        try:
            file_convention = FileConventionRead(from_file=file)
        except:
            pass
    
    if not isinstance(file_convention, FileConventionRead):
        
        raise FileConventionError('Unknown file convention: {}'
                                  .format(file_convention))
        
    finfo = file_convention.get_info_from_file(file)
    ts_type = finfo['ts_type']
    year = finfo['year']
    if not ts_type in const.GRID_IO.TS_TYPES:
        raise FileConventionError('Invalid ts_type in file: {}'.format(ts_type))
    elif not -2000 <= year <= 20000:
        raise FileConventionError('Invalid year in file: {}'.format(year))
    try:
        check_time_coord(cube, ts_type, year)
    except UnresolvableTimeDefinitionError as e:
        raise UnresolvableTimeDefinitionError(repr(e))
    except:
        msg = ("Invalid time dimension coordinate in file {}. " 
               .format(os.path.basename(file)))
        logger.warning(msg)
        if const.GRID_IO.CORRECT_TIME_FILENAME:
            logger.warning("Attempting to correct time coordinate "
                           "using information in file name")
            try:
                cube = correct_time_coord(cube, 
                                          ts_type=finfo["ts_type"],
                                          year=finfo["year"]) 
            except:
                pass
        if const.WRITE_FILEIO_ERR_LOG:
            add_file_to_log(file, 'Invalid time dimension')
    return cube
    
def _check_leap_year(num, num_per, ts_type):
    if ts_type == 'daily' and num + 1 == num_per:
        return True
    elif ts_type == '3hourly' and num + 8 == num_per:
        return True
    elif ts_type == 'hourly' and num + 24 == num_per:
        return True
    return False
def check_time_coord(cube, ts_type, year):
    """Method that checks the time coordinate of an iris Cube
    
    This method checks if the time dimension of a cube is accessible and 
    according to the standard (i.e. fully usable). It only checks, and does not
    correct. For the latter, please see :func:`correct_time_coord`.
    
    Parameters
    ----------
    cube : Cube
        cube containing data
    ts_type : str
        pyaerocom ts_type
    year : 
        year of data
    
    Returns
    -------
    bool
        True, if time dimension is ok, False if not
    """
    try:
        t = cube.coord("time")
    except:
        raise AttributeError("Cube does not contain time dimension")
    if not isinstance(t, iris.coords.DimCoord):
        raise AttributeError("Time is not a DimCoord instance")
    try:
        cftime_to_datetime64(0, cfunit=t.units)
    except:
        raise ValueError("Could not convert time unit string")

    tidx = make_datetimeindex(ts_type, year)
    
    num_per = len(tidx)
    num = len(t.points)

    if not num == num_per:
        if tidx[0].is_leap_year:
            if not _check_leap_year(num, num_per, ts_type):
                raise UnresolvableTimeDefinitionError('Expected {} timestamps but '
                                                  'data has {}'
                                                  .format(len(tidx), num))
        else:
            raise UnresolvableTimeDefinitionError('Expected {} timestamps but '
                                                  'data has {}'
                                                  .format(len(tidx), num))
        
    
    pstr = TS_TYPE_TO_PANDAS_FREQ[ts_type]
    # ToDo: check why MS is not working for period conversion
    if pstr == 'MS':
        pstr = 'M'
    # convert first and last timestamps of index array into periods 
    # (e.g. January and December for monthly data)
    per0 = tidx[0].to_period(pstr)
    per1 = tidx[-1].to_period(pstr)    
    
    # first and last timestamp in data
    t0, t1 = cftime_to_datetime64([t.points[0], t.points[-1]], cfunit=t.units)
    
    if not per0.start_time <= t0 <= per0.end_time:
        raise ValueError('First timestamp of data {} does not lie in first '
                         'period: {}'.format(t0, per0))
    elif not per1.start_time <= t1 <= per1.end_time:
        raise ValueError('Last timestamp of data {} does not lie in last '
                         'period: {}'.format(t1, per1))
        

def correct_time_coord(cube, ts_type, year):
    """Method that corrects the time coordinate of an iris Cube
    
    Parameters
    ----------
    cube : Cube
        cube containing data
    ts_type : str
        temporal resolution of data (e.g. "hourly", "daily"). This information
        is e.g. encrypted in the filename of a NetCDF file and may be 
        accessed using :class:`pyaerocom.io.FileConventionRead`
    year : int
        interger specifying year of observation, e.g. 2017
    tindex_cube : int
        index of time dimension in Cube
    
    Returns
    -------
    Cube
        the same instance of the input cube with corrected time dimension axis
        
    """
    tindex_cube = None
    dim_lens = []
    for i, coord in enumerate(cube.dim_coords):
        dim_lens.append(len(coord.points))
        if coord.name() == 'time':
            tindex_cube = i
    if tindex_cube is None:
        if cube.ndim != len(cube.dim_coords): #one dimension is missing
            for idx, dim_len in enumerate(cube.shape):
                if not dim_len in dim_lens: #candidate
                    tindex_cube = idx
    if tindex_cube is None:
        raise NetcdfError('Failed to identify data index of time dimension in '
                          'cube {}'.format(repr(cube)))
    tres_str = TSTR_TO_CF[ts_type]
    conv = TSTR_TO_NP_DT[ts_type]
    tunit_str = '%s since %s-01-01 00:00:00' %(tres_str, year)
    num = cube.shape[tindex_cube]

    tunit = cf_units.Unit(tunit_str, calendar=cf_units.CALENDAR_STANDARD)
    tres_np = TSTR_TO_NP_TD[ts_type]
    base = datetime64("%s-01-01 00:00:00" %year).astype(conv)
    times = base + arange(0, num, 1).astype(tres_np)
    # see this thread https://github.com/matplotlib/matplotlib/issues/2259/
    times_dt = times.astype("datetime64[s]").astype(datetime)
#    timestamps = datetime64(str(year)) + 
    time_nums = [tunit.date2num(t) for t in times_dt]
    tcoord = iris.coords.DimCoord(time_nums, standard_name='time', units=tunit)
        
    #tcoord_dim = cube.coord_dims('time')
    try:
        cube.remove_coord('time')
    except:
        pass
    cube.add_dim_coord(tcoord, tindex_cube)
    return cube

def concatenate_iris_cubes(cubes, error_on_mismatch=True):
    """Concatenate list of :class:`iris.Cube` instances cubes into single Cube
    
    Helper method for concatenating list of cubes and that helps 
    with handling the fact that the corresponding iris method is not well 
    defined in the sense of what it returns (i.e. instance of 
    :class:`Cube` or :class:`CubeList`, depending on whether all cubes 
    could be concatenated or not...)
    
    This method is not supposed to be called directly but rather 
    :func:`concatenate_cubes` (which ALWAYS returns instance of 
    :class:`Cube` or raises Exception) or :func:`concatenate_possible_cubes`
    (which ALWAYS returns instance of :class:`CubeList` or raises Exception)
    
    Parameters
    ----------
    cubes : CubeList
        list of individual cubes
    error_on_mismatch
        boolean specifying whether an Exception is supposed to be raised
        or not
        
    Returns
    -------
    :obj:`Cube` or :obj:`CubeList`
        result of concatenation 
    
    Raises
    ------
    iris.exceptions.ConcatenateError
        if ``error_on_mismatch=True`` and input cubes could not all concatenated
        into a single instance of :class:`iris.Cube` class.
        
    """
    var_name = cubes[0].var_name
    if const.GRID_IO.EQUALISE_METADATA:
        meta_init = cubes[0].metadata
        if not all([x.metadata == meta_init for x in cubes]):
            logger.warning("{} cubes to be concatenated have different meta "
                           "data settings. These will be unified using the "
                           "metadata dictionary of the first cube "
                           "(otherwise the method concatenate of the iris "
                           "package won't work)".format(var_name))
            for cube in cubes:
                cube.metadata = meta_init
                
    #now put the CubeList together and form one cube
    #1st equalise the cubes (remove non common attributes)
    equalise_attributes(cubes)
    #unify time units
    iris.util.unify_time_units(cubes)
    
    #now concatenate the cube list to one cube
    cubes_concat = iris._concatenate.concatenate(cubes, error_on_mismatch)
    
    return cubes_concat[0]

if __name__== "__main__":
    import pyaerocom as pya
    
    r = pya.io.ReadGridded('BCC-CUACE_HIST')
    
    d = r.read_var('zg')
    print(d)
    
    