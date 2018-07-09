#!/usr/bin/env python3

################################################################
# readgridded.py
#
# model data reading class
#
# this file is part of the aerocom_pt package
#
#################################################################
# Created 20171030 by Jan Griesfeller for Met Norway
#
# Last changed: See git log
#################################################################

#Copyright (C) 2017 met.no
#Contact information:
#Norwegian Meteorological Institute
#Box 43 Blindern
#0313 OSLO
#NORWAY
#E-mail: jan.griesfeller@met.no
#This program is free software; you can redistribute it and/or modify
#it under the terms of the GNU General Public License as published by
#the Free Software Foundation; either version 3 of the License, or
#(at your option) any later version.
#This program is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#GNU General Public License for more details.
#You should have received a copy of the GNU General Public License
#along with this program; if not, write to the Free Software
#Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#MA 02110-1301, USA

from glob import glob
from re import match
from os.path import isdir, basename
from collections import OrderedDict as od
from numpy import arange
from pandas import Timestamp

from iris import Constraint, load_cube
from iris.cube import CubeList
from iris.experimental.equalise_cubes import equalise_attributes
from iris.util import unify_time_units
from iris._concatenate import concatenate

from pyaerocom import const
from pyaerocom.exceptions import IllegalArgumentError
from pyaerocom.io.fileconventions import FileConventionRead
from pyaerocom.io.helpers import (check_time_coord, correct_time_coord,
                                  search_data_dir_aerocom)
from pyaerocom.griddeddata import GriddedData

class ReadGridded(object):
    """Class for reading gridded files based on network or model ID
    
    Note
    ----
    The reading only works if files are stored using a valid file naming 
    convention. See package data file `file_conventions.ini <http://
    aerocom.met.no/pyaerocom/config_files.html#file-conventions>`__ for valid
    keys. You may define your own fileconvention in this file, if you wish.
    
    Attributes
    ----------
    name : str
        string ID for model or obsdata network (see e.g. Aerocom interface map
        plots lower left corner)
    data : GriddedData
        imported data object 
    data_dir : str
        directory containing result files for this model
    start_time : pandas.Timestamp
        start time for data import
    stop_time : pandas.Timestamp
        stop time for data import
    file_convention : FileConventionRead
        class specifying details of the file naming convention for the model
    files : list
        list containing all filenames that were found.
        Filled, e.g. in :func:`ReadGridded.get_model_files`
    from_files : list
        List of all netCDF files that were used to concatenate the current 
        data cube (i.e. that can be based on certain matching settings such as
        var_name or time interval). 
    vars : list
        list containing all variable names that were found
        
    Parameters
    ----------
    name : str
        string ID of model (e.g. "AATSR_SU_v4.3","CAM5.3-Oslo_CTRL2016")
    start_time : :obj:`pandas.Timestamp` or :obj:`str`, optional
        desired start time of dataset (note, that strings are passed to 
        :class:`pandas.Timestamp` without further checking)
    stop_time : :obj:`pandas.Timestamp` or :obj:`str`, optional
        desired stop time of dataset (note, that strings are passed to 
        :class:`pandas.Timestamp` without further checking)
    file_convention : str
        string ID specifying the file convention of this model (cf. 
        installation file `file_conventions.ini <https://github.com/metno/
        pyaerocom/blob/master/pyaerocom/data/file_conventions.ini>`__)
    init : bool
        if True, the model directory is searched (:func:`search_data_dir`) on
        instantiation and if it is found, all valid files for this model are 
        searched using :func:`search_all_files`.
    verbose : bool
        if True, output is printed
        
    Examples
    --------
    
        >>> read = ReadGridded(name="ECMWF_OSUITE")
        >>> read.read_var("od550aer")
        >>> read.read_var("od550so4")
        >>> read.read_var("od550bc")
        >>> print(data.short_str()) for data in read.data
        
    """
    _start_time = None
    _stop_time = None
    # Directory containing model data for this species
    _data_dir = ""
    def __init__(self, name="", start_time=None, stop_time=None,
                 file_convention="aerocom3", io_opts=const, init=True, 
                 verbose=const.VERBOSE):
        # model ID
        if not isinstance(name, str):
            if isinstance(name, list):
                msg = ("Input for name is list. You might want to use "
                       "class ReadGriddedMulti for import?")
            else:
                msg = ("Invalid input for name. Need str, got: %s"
                       %type(name))
            raise TypeError(msg)
                
        self.name = name
        
        # only overwrite if there is input, note that the attributes
        # start_time and stop_time are defined below as @property getter and
        # setter methods, that ensure that the input is convertible to 
        # pandas.Timestamp
        if start_time:
            self.start_time = start_time
        if stop_time:
            self.stop_time = stop_time
        
        self.verbose = verbose
        
        # Dictionary containing loaded results for different variables
        self.data = od()
        
        # file naming convention. Default is aerocom3 file convention, change 
        # using self.file_convention.import_default("aerocom2"). Is 
        # automatically updated in class ReadGridded
        self.io_opts = io_opts
        self.file_convention = FileConventionRead(file_convention)
        
        # All files that were found for this model (updated, e.g. in class
        # ReadGridded, method: `get_model_files`
        self.files = []
        
        self._match_files = None
        self.vars = []
        self.years = []
        
        if init and name:
            self.search_data_dir()
            self.search_all_files()
                
    @property
    def data_dir(self):
        """Model directory"""
        dirloc = self._data_dir
        if not isdir(dirloc):
            raise IOError("Model directory for ID %s not available or does "
                          "not exist" %self.name)
        return dirloc
    
    @data_dir.setter
    def data_dir(self, value):
        if isinstance(value, str) and isdir(value):
            self._data_dir = value
        else:
            raise ValueError("Could not set directory: %s" %value)
            
    @property
    def file_type(self):
        """File type of data files"""
        return self.io_opts.GRID_IO.FILE_TYPE
    
    @property
    def TS_TYPES(self):
        """List with valid filename encryptions specifying temporal resolution
        """
        return self.io_opts.GRID_IO.TS_TYPES
    
    @property
    def start_time(self):
        """Start time of the dataset
        
        Note      
        ----
        If input is not :class:`pandas.Timestamp`, it must be convertible 
        into :class:`pandas.Timestamp` (e.g. "2012-1-1")
        """
        return self._start_time

    @start_time.setter
    def start_time(self, value):
        if not isinstance(value, str):
            try:
                value = str(value)
            except:
                raise ValueError("Failed to convert non-string input for "
                                 "time stamp into string")
        if not isinstance(value, Timestamp):    
            try:
                value = Timestamp(value)
            except:
                raise ValueError("Failed to convert input value to pandas "
                                  "Timestamp: %s" %value)
        self._start_time = value
            
    @property
    def stop_time(self):
        """Stop time of the dataset
        
        Note      
        ----
        If input is not :class:`pandas.Timestamp`, it must be convertible 
        into :class:`pandas.Timestamp` (e.g. "2012-1-1")
        
        """
        return self._stop_time
    
    @stop_time.setter
    def stop_time(self, value):
        if not isinstance(value, str):
            try:
                value = str(value)
            except:
                raise ValueError("Failed to convert non-string input for "
                                 "time stamp into string")
        if not isinstance(value, Timestamp):  
            try:
                value = Timestamp(value)
            except:
                raise ValueError("Failed to convert input value to pandas "
                                  "Timestamp: %s" %value)
        self._stop_time = value
    
    @property
    def years_to_load(self):
        """Array containing year numbers that are supposed to be loaded
        
        Returns
        -------
        ndarray
        """
        if self.start_time and self.stop_time:
            return arange(self.start_time.year, self.stop_time.year + 1, 1)
        if not self.years:
            raise AttributeError("No information available for available "
                                 "years. Please run method "
                                 "search_all_files first")
        return self.years
    
    def search_data_dir(self):
        """Search data directory based on model ID
        
        Wrapper for method :func:`search_data_dir_aerocom`
        
        Returns
        -------
        str
            data directory
        
        Raises
        ------
        IOError 
            if directory cannot be found
        """
        _dir = search_data_dir_aerocom(self.name, verbose=self.verbose)
        self.data_dir = _dir
        return _dir
    
    # get the model directory (note that the folder "renamed" is used)
    def search_all_files(self, update_file_convention=True):
        """Search all valid model files for this model
        
        
        This method 
        
        Parameters
        ----------
        update_file_convention : bool
            if True, the first file in `data_dir` is used to identify the
            file naming convention (cf. :class:`FileConventionRead`)
            
        Note
        ----
        This function does not seperate by variable or time, it gets you all
        valid files for all variables and times for this model.
        """
        # get all netcdf files in folder
        nc_files = glob(self.data_dir + '/*{}'.format(self.file_type))
        if update_file_convention:
            # Check if the found file has a naming according the aerocom conventions
            # and set the convention for all files (maybe this need to be 
            # updated in case there can be more than one file naming convention
            # within one model directory)
            ok = False
            for file in nc_files:
                try:
                    self.file_convention.from_file(basename(file))
                    ok = True
                    break
                except:
                    pass
            if not ok:
                raise IOError("Failed to identify file naming convention "
                              "from files in model directory for model "
                              "%s\ndata_dir: %s"
                              %(self.name, self.data_dir))
        _vars_temp = []
        _years_temp = []
        for _file in nc_files:
            try:
                info = self.file_convention.get_info_from_file(_file)
                _vars_temp.append(info["var_name"])
                _years_temp.append(info["year"])
                self.files.append(_file)
            except Exception as e:
                if self.verbose:
                    print("Failed to import file %s\nError: %s" 
                          %(basename(_file), repr(e)))
        if not _vars_temp or not len(_vars_temp) == len(_years_temp):
            raise IOError("Failed to extract information from filenames")
        # make sorted list of unique vars
        self.vars = sorted(od.fromkeys(_vars_temp))
        self.years = sorted(od.fromkeys(_years_temp))
        
    def update(self, **kwargs):
        """Update one or more valid parameters
        
        Parameters
        ----------
        **kwargs
            keyword args that will be used to update (overwrite) valid class 
            attributes such as `data, data_dir, files`
        """
        for k, v in kwargs.items():
            if k in self.__dict__:
                print("Updating %s in ModelImportResult for model %s"
                      "New value: %s" %(k, self.name, v))
                self.__dict__[k] = v
            else:
                print("Ignoring key %s in ModelImportResult.update()"  %k)
                
    def read_var(self, var_name, start_time=None, stop_time=None, 
                 ts_type='daily'):
        """Read model data for a specific variable
        
        This method searches all valid files for a given variable and for a 
        provided temporal resolution (e.g. *daily, monthly*), optionally
        within a certain time window, that may be specified on class 
        instantiation or using the corresponding input parameters provided in 
        this method.
        
        The individual NetCDF files for a given temporal period are loaded as
        instances of the :class:`iris.Cube` object and appended to an instance
        of the :class:`iris.cube.CubeList` object. The latter is then used to 
        concatenate the individual cubes in time into a single instance of the
        :class:`pyaerocom.GriddedData` class. In order to ensure that this
        works, several things need to be ensured, which are listed in the 
        following and which may be controlled within the global settings for 
        NetCDF import using the attribute :attr:`GRID_IO` (instance of
        :class:`OnLoad`) in the default instance of the 
        :class:`pyaerocom.config.Config` object accessible via 
        ``pyaerocom.const``.
        
        
        Parameters
        ----------
        var_name : str
            variable name that is supposed to be plotted (e.g. )
            Must be in :attr:`vars`
        start_time : :obj:`Timestamp` or :obj:`str`, optional
            start time of data import (if valid input, then the current 
            :attr:`start_time` will be overwritten)
        stop_time : :obj:`Timestamp` or :obj:`str`, optional
            stop time of data import (if valid input, then the current 
            :attr:`start_time` will be overwritten)
        ts_type : str
            string specifying temporal resolution (choose from 
            "hourly", "3hourly", "daily", "monthly")
            
        Returns
        -------
        GriddedData
            loaded data object
        """
        if not ts_type in self.TS_TYPES:
            raise ValueError("Invalid input for ts_type, got: {}, "
                             "allowed values: {}".format(ts_type, 
                                                         self.TS_TYPES))
        if start_time:
            self.start_time = start_time
        if stop_time:
            self.stop_time = stop_time
        
        if var_name not in self.vars:
            raise ValueError("Error: variable {} not found in files contained "
                             "in model directory: {}".format(var_name, 
                                                  self.data_dir))
        
        match_files = []
        for year in self.years_to_load:
            if const.MIN_YEAR <= year <= const.MAX_YEAR:
                # search for filename in self.files using ts_type as default ts size
                for _file in self.files:
                    #new file naming convention (aerocom3)
                    match_mask = self.file_convention.string_mask(var_name,
                                                                  year, 
                                                                  ts_type)
                    if match(match_mask, _file):
                        match_files.append(_file)
                        if self.verbose:
                            print("FOUND MATCH: {}".format(basename(_file)))

            else:
                if self.verbose:
                    print("Ignoring file {}. File out of allowed year bounds "
                          "({:d} - {:d})" %(basename(_file), 
                                            const.MIN_YEAR, 
                                            const.MAX_YEAR))
           
        if len(match_files) == 0:
            raise IOError("No files could be found for dataset %s, variable %s "
                          "and %s data in specified time interval %s-%s"
                          %(self.name, var_name, ts_type, self.start_time,
                            self.stop_time))
# =============================================================================
#             try:
#                 freqs = list(self.TS_TYPES)
#                 ts_type = freqs[freqs.index(ts_type)+1]
#                 print("No files could be found for variable %s, and %s "
#                       "data in specified time interval\n%s-%s. Trying "
#                       "ts_type {}".format(ts_type)
#                       %(self.name, ts_type, self.start_time,
#                         self.stop_time))
#                 return self.read(var_name, start_time, stop_time, ts_type)
#             except:
# =============================================================================
                
                
        self._match_files = match_files
        # Define Iris var_constraint -> ensures that only the current 
        # variable is extracted from the netcdf file 
        var_constraint = Constraint(cube_func=lambda c: c.var_name==var_name)
        
        # read files using iris
        cubes = CubeList()
        loaded_files = []
        for _file in match_files:
            try:
                finfo = self.file_convention.get_info_from_file(_file)
                cube = load_cube(_file, var_constraint)
                if const.GRID_IO["CHECK_TIME_FILENAME"]:
                    
                    if not check_time_coord(cube, ts_type=finfo["ts_type"], 
                                            year=finfo["year"],
                                            verbose=self.verbose):
                        
                        if self.verbose:
                            print("Invalid time axis in file {}. " 
                                             "Attempting to correct.".format(
                                                     basename(_file)))
                        
                        cube = correct_time_coord(cube, 
                                                  ts_type=finfo["ts_type"],
                                                  year=finfo["year"])
                        
                else:
                    if self.verbose:
                        print("WARNING: Automatic check of time "
                              "array in netCDF files is deactivated."
                              " This may cause problems in case "
                              "the time dimension is not CF conform.")
                
                cubes.append(cube)
                loaded_files.append(_file)
            except Exception as e:
                if self.verbose:
                    print("Failed to load {} as Iris cube.\n"
                          "Error: {}".format(_file, repr(e)))
        
        if len(loaded_files) == 0:
            raise IOError("None of the found files for variable {}, and {} "
                          "in specified time interval\n{}-{}\n"
                          "could be loaded".format(self.name,
                                                   ts_type, 
                                                   self.start_time,
                                                   self.stop_time))
        if const.GRID_IO.EQUALISE_METADATA:
            meta_init = cubes[0].metadata
            if not all([x.metadata == meta_init for x in cubes]):
                if self.verbose:
                    print("Cubes for variable {} have different meta data "
                          "settings. These will be unified using the metadata "
                          "dictionary of the first cube (otherwise the method "
                          "concatenate of the iris package won't work)".format(
                          var_name))
                for cube in cubes:
                    cube.metadata =meta_init
            
        #now put the CubeList together and form one cube
        #1st equalise the cubes (remove non common attributes)
        equalise_attributes(cubes)
        #unify time units
        unify_time_units(cubes)
        self._cubes = cubes
        #now concatenate the cube list to one cube
        cubes_concat = concatenate(cubes, error_on_mismatch=True)
        if len(cubes_concat) > 1:
            long_names = [x.long_name for x in cubes_concat]
            raise IOError("Could not concatenate individual Cubes for in "
                          "var_name {} in time: likely due to multiple "
                          "long_name attributes in source files: {}".format(
                                  var_name, long_names))
        
        #create instance of pyaerocom.GriddedData
        data = GriddedData(input=cubes_concat[0], from_files=loaded_files,
                         name=self.name, ts_type=ts_type, 
                         verbose=self.verbose)
        # crop cube in time (if applicable)
        if self.start_time and self.stop_time:
            if self.verbose:
                print("Applying temporal cropping of result cube")
            try:
# =============================================================================
#                 t_constraint = data.get_time_constraint(self.start_time, 
#                                                         self.stop_time)
#                 _data = data.extract(t_constraint)
# =============================================================================
                _data = data.crop(time_range=(self.start_time,
                                              self.stop_time))
                data = _data
            except Exception as e:
                if self.verbose:
                    print("Failed to crop data for {} in time.\n"
                          "Error: {}".format(var_name, repr(e)))
        
        if var_name in self.data and self.verbose:
            print("Warning: Data for variable {} already exists "
                             "and will be overwritten".format(var_name))
        self.data[var_name] = data
        return data
    
    def read(self, var_names=None, start_time=None, stop_time=None, 
                 ts_type='daily'):
        """Read all variables that could be found 
        
        Reads all variables that are available (i.e. in :attr:`vars`)
        
        Parameters
        ----------
        **kwargs
            see :func:`read_var` for valid input arguments.
        
        Returns
        -------
        tuple
            loaded data objects (type GriddedData)
        """
        _vars_read = []
        _loaded = []
        if var_names is None:
            var_names = self.vars
        elif isinstance(var_names, str):
            var_names = [var_names]
        elif not isinstance(var_names, list):
            raise IOError("Invalid input for var_names {}. Need string or list "
                          "of strings specifying var_names to load. You may "
                          "also leave it empty (None) in which case all "
                          "available variables are loaded".format(var_names))
        for var in var_names:
            try:
                dat = self.read_var(var, start_time, stop_time, ts_type)
                _vars_read.append(var)
                _loaded.append(dat)
            except Exception as e:
                print("Failed to read variable {}."
                      "Error msg: {}".format(var, repr(e)))
                _loaded.append(None)
        self.vars = _vars_read
        return tuple(_loaded)
    
    def __getitem__(self, var_name):
        """Try access import result for one of the models
        
        Parameters
        ----------
        var_name : str
            string specifying variable that is supposed to be extracted
        
        Returns
        -------
        GriddedData
            the corresponding read class for this model
            
        Raises
        -------
        ValueError
            if results for ``var_name`` are not available
        """
        if not var_name in self.data:
            raise ValueError("No data found for variable %s" %var_name)
        return self.data[var_name]
    
    def __str__(self):
        head = "Pyaerocom {}".format(type(self).__name__)
        s = ("\n{}\n{}\n"
             "Model ID: {}\n"
             "Available variables: {}\n"
             "Available years: {}\n".format(head, 
                                            len(head)*"-",
                                            self.name,
                                            self.vars, 
                                            self.years))
        if self.data:
            s += "\nLoaded GriddedData objects:\n"
            for var_name, data in self.data.items():
                s += "{}\n".format(data.short_str())
        return s.rstrip()
        
class ReadGriddedMulti(object):
    """Class for import of AEROCOM model data from multiple models
    
    This class provides an interface to import model results from an arbitrary
    number of models and specific for a certain time interval (that can be 
    defined, but must not be defined). Largely based on 
    :class:`ReadGridded`.
    
    ToDo
    ----
    
    Sub-class from ReadGridded
    
    Note
    ----
    The reading only works if files are stored using a valid file naming 
    convention. See package data file `file_conventions.ini <http://
    aerocom.met.no/pyaerocom/config_files.html#file-conventions>`__ for valid
    keys. You may define your own fileconvention in this file, if you wish.
    
    Attributes
    ----------
    names : list
        list containing string IDs of all models that should be imported
    results : dict
        dictionary containing :class:`ReadGridded` instances for each
        name
    
    Examples
    --------
    >>> import pyaerocom, pandas
    >>> start, stop = pandas.Timestamp("2012-1-1"), pandas.Timestamp("2012-5-1")
    >>> models = ["AATSR_SU_v4.3", "CAM5.3-Oslo_CTRL2016"]
    >>> read = pyaerocom.io.ReadGriddedMulti(models, start, stop, verbose=False)
    >>> print(read.names)
    ['AATSR_SU_v4.3', 'CAM5.3-Oslo_CTRL2016']
    >>> read_cam = read['CAM5.3-Oslo_CTRL2016']
    >>> assert type(read_cam) == pyaerocom.io.ReadGridded
    >>> for var in read_cam.vars: print(var)
    abs550aer
    deltaz3d
    humidity3d
    od440aer
    od550aer
    od550aer3d
    od550aerh2o
    od550dryaer
    od550dust
    od550lt1aer
    od870aer
    """
    # "private attributes (defined with one underscore). These may be 
    # controlled using getter and setter methods (@property operator, see 
    # e.g. definition of def start_time below)
    _start_time = None
    _stop_time = None
    def __init__(self, names, start_time=None, stop_time=None,
                 verbose=const.VERBOSE):
        
        if isinstance(names, str):
            names = [names]
        if not isinstance(names, list) or not all([isinstance(x, str) for x in names]):
            raise IllegalArgumentError("Please provide string or list of strings")
    
        self.names = names
        # dictionary containing instances of ModelImportResult for each model
        # is initiated in method `init_results` at end of __init__
        self.results = None
        
        self.verbose = verbose
        
        # only overwrite if there is input, note that the attributes
        # start_time and stop_time are defined below as @property getter and
        # setter methods, that ensure that the input is convertible to 
        # pandas.Timestamp
        if start_time:
            self.start_time = start_time
        if stop_time:
            self.stop_time = stop_time
        
        self.init_results()
        self.search_data_dirs()
        self.search_all_files()
        
    @property
    def start_time(self):
        """Start time for the data import
        
        Note      
        ----
        If input is not :class:`pandas.Timestamp`, it must be convertible 
        into :class:`pandas.Timestamp` (e.g. "2012-1-1")
        """
        return self._start_time
# =============================================================================
#         if not isinstance(t, Timestamp):
#             raise ValueError("Invalid value encountered for start time "
#                              "in reading engine: %s" %t)
#         return t
# =============================================================================
    
    @start_time.setter
    def start_time(self, value):
        if not isinstance(value, str):
            try:
                value = str(value)
            except:
                raise ValueError("Failed to convert non-string input for "
                                 "time stamp into string")
        if not isinstance(value, Timestamp):    
            try:
                value = Timestamp(value)
            except:
                raise ValueError("Failed to convert input value to pandas "
                                  "Timestamp: %s" %value)
        self._start_time = value
            
    @property
    def stop_time(self):
        """Stop time for the data import
        
        Note      
        ----
        If input is not :class:`pandas.Timestamp`, it must be convertible 
        into :class:`pandas.Timestamp` (e.g. "2012-1-1")
        
        """
        return self._stop_time
# =============================================================================
#         if not isinstance(t, Timestamp):
#             raise ValueError("Invalid value encountered for stop time "
#                              "in reading engine: %s" %t)
#         return t
# =============================================================================
    
    @stop_time.setter
    def stop_time(self, value):
        if not isinstance(value, str):
            try:
                value = str(value)
            except:
                raise ValueError("Failed to convert non-string input for "
                                 "time stamp into string")
        if not isinstance(value, Timestamp):  
            try:
                value = Timestamp(value)
            except:
                raise ValueError("Failed to convert input value to pandas "
                                  "Timestamp: %s" %value)
        self._stop_time = value
        
    
    
    def init_results(self):
        """Initiate the import result attributes
        
        Creates and initiates :class:`ModelImportResult` object for each 
        model specified in :attr:`names` and stores it in the dictionary
        :attr:`results` using the `name`.
        """
        self.results = od()
        for name in self.names:
            self.results[name] = ReadGridded(name,
                                                   self.start_time, 
                                                   self.stop_time, 
                                                   init=False,
                                                   verbose=self.verbose)
    
    def search_data_dirs(self):
        """Get the directory where model data for a given model resides in
        
        Returns
        -------
        bool
            True, if directory could be found, else False
        """
        #remember only the model IDs for which a directory could be found
        names_new = []
        for name in self.names:
            # loop through the list of models
            if self.results[name].search_data_dir():
                names_new.append(name)
        if len(names_new) == 0:
            raise AttributeError("Failed to find model directories for all "
                                 "model IDs specified (%s)" %self.names)
        self.names = names_new
        return names_new
    
    def search_all_files(self):
        """Search all valid model files for each model
        
        See also :func:`ReadGridded.search_all_files`
        
        Note
        ----
        This function does not seperate by variable or time.
        
        """
        # unfortunately there's more than one file naming convention
        # examples
        # aerocom3_CAM5.3-Oslo_AP3-CTRL2016-PD_od550aer_Column_2010_monthly.nc
        # aerocom.AATSR_ensemble.v2.6.daily.od550aer.2012.nc
        # loop through the list of models
        for name in self.names:
            self.results[name].search_all_files()
    
        
    def read(self, var_ids, names=None, start_time=None, stop_time=None,
             ts_type="daily"):
        """High level method to import data for multiple variables and models
        
        Parameters
        ----------
        var_ids : :obj:`str` or :obj:`list`
            string IDs of all variables that are supposed to be imported
        names : :obj:`str` or :obj:`list`, optional
            string IDs of all models that are supposed to be imported
        start_time : :obj:`Timestamp` or :obj:`str`, optional
            start time of data import (if valid input, then the current 
            :attr:`start_time` will be overwritten)
        stop_time : :obj:`Timestamp` or :obj:`str`, optional
            stop time of data import (if valid input, then the current 
            :attr:`start_time` will be overwritten)
        ts_type : str
            string specifying temporal resolution (choose from 
            "hourly", "3hourly", "daily", "monthly")
            
        Returns
        -------
        dict
            result dictionary
            
        Examples
        --------
        
            >>> read = ReadGriddedMulti(names=["ECMWF_CAMS_REAN",
            ...                                      "ECMWF_OSUITE"],
            ...                           verbose=False)
            >>> read.read(["od550aer", "od550so4", "od550bc"])
            
        """
        if start_time:
            self.start_time = start_time
        if stop_time:
            self.stop_time = stop_time

        if names is None: #use all models if unspecified
            names = self.names
        elif isinstance(names, str):
            names = [names]
        if isinstance(var_ids, str):
            var_ids = [var_ids]
            
        warnings = []
        for name in names:
            if name in self.results:
                read = self.results[name]
                for var in var_ids:
                    if var in read.vars:
                        try:
                            read.read_var(var, start_time, stop_time, ts_type)
                        except Exception as e:
                            print(repr(e))
                            
                    else:
                        warnings.append("Variable {} not available for model "
                                        "{}".format(var, name))
                    
                
            else:
                warnings.append("Failed to import model {}".format(name))
        if self.verbose:
            for msg in warnings:
                print(msg)
        return self.results
    
    def __getitem__(self, name):
        """Try access import result for one of the models
        
        Parameters
        ----------
        name : str
            string specifying model that is supposed to be extracted
        
        Returns
        -------
        ReadGridded
            the corresponding read class for this model
            
        Raises
        -------
        ValueError
            if results for ``name`` are not available
        """
        if not name in self.results:
            raise ValueError("No data found for name %s" %name)
        return self.results[name]
    
    def __str__(self):
        head = "Pyaerocom %s" %type(self).__name__
        s = ("\n%s\n%s\n"
             "Model IDs: %s\n" %(head, len(head)*"-", self.names))
        if self.results:
            s += "\nLoaded data:"
            for name, read in self.results.items():
                s += "\n%s" %read
        return s
    
if __name__=="__main__":
    
    import iris
    
    read = ReadGridded("ECHAM6-SALSA_AP3-CTRL2015", verbose=True)
    
    cube = iris.load_cube(read.files[0])
    
    data = read.read_var("od550aer", "2009", "2011", ts_type="monthly")
    
    
    
    
    
# =============================================================================
#     read = ReadGridded(name="ECMWF_CAMS_REAN",
#                                   start_time="1-1-2003",
#                                   stop_time="31-12-2007", 
#                                   verbose=True)
#     data = read.read_var(var_name="od550aer", ts_type="daily")
#     
# =============================================================================
    
# =============================================================================
#     read = ReadGriddedMulti(names=["ECMWF_CAMS_REAN", "ECMWF_OSUITE"])
#     
#     read.read(["od550aer", "od440aer"])
#     
#     print(read)
# =============================================================================
# =============================================================================
#     
#     import doctest
#     doctest.testmod()
# 
# =============================================================================

    

