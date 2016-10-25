import os
import csv
import numpy as np
try:
   from netCDF4 import Dataset as netcdf
except:
   from scipy.io.netcdf import netcdf_file as netcdf
import verif.location
import verif.util
import verif.variable
import verif.field


def get_input(filename):
   if(not os.path.exists(filename)):
      verif.util.error("File '" + filename + "' does not exist")
   if(verif.input.NetcdfCf.is_valid(filename)):
      input = verif.input.NetcdfCf(filename)
   elif(verif.input.Comps.is_valid(filename)):
      input = verif.input.Comps(filename)
   elif(verif.input.Text.is_valid(filename)):
      input = verif.input.Text(filename)
   else:
      verif.util.error("File '" + filename + "' is not a valid input file")
   return input


class Input(object):
   """ Base class representing verification data

   Stores observation and forecast data

   Class attributes:
   description (str): A description of the parser

   Instance attributes:
   name:          A string name identifying the dataset (such as a filename)
   fullname:      A string name identifying the dataset (such as a filename)
   shortname:     A string name identifying the dataset (such as a filename)
   variable:      A verif.Variable representing the stored in the input

   dates:         A numpy array of avilable dates
   offsets:       A numpy array of available leadtimes
   locations:      A list of available locations
   thresholds:    A numpy array of available thresholds
   quantiles:     A numpy array of available quantiles

   obs:           A 3D numpy array with dims (date,offset,location)
   deterministic: A 3D numpy array with dims (date,offset,location)
   ensemble:      A 4D numpy array with dims (date,offset,location,member)
   threshold_scores (cdf?): A 4D numpy array with dims (date,offset,location, threshold)
   quantile_scores: A 4D numpy array with dims (date,offset,location, quantile)
   """
   description = None  # Overwrite this

   def get_variables(self):
      variables = [verif.field.Obs, verif.field.Deterministic]
      thresholds = [verif.field.Threshold(threshold) for threshold in self.thresholds]
      quantiles = [verif.field.Quantiles(quantile) for quantile in self.quantiles]
      return variables + thresholds + quantiles

   @property
   def name(self):
      """ Default to setting the name to the filename without the path """
      I = self.fullname.rfind('/')
      name = self.fullname[I + 1:]
      return name

   @property
   def shortname(self):
      """ Default to setting the name to the filename without the path and extension"""
      I = self.name.rfind('.')
      name = self.name[:I]
      return name


class Comps(Input):
   """
   Original fileformat used by OutputVerif in COMPS
   """
   _dimensionNames = ["Date", "Offset", "Location", "Lat", "Lon", "Elev"]
   description = verif.util.format_argument("netcdf", "Undocumented legacy " +
         "NetCDF format, to be phased out. A new NetCDF based format will " +
         "be defined.")

   def __init__(self, filename):
      self.fullname = filename
      self._filename = os.path.expanduser(filename)
      self._file = netcdf(self._filename, 'r')

      # Pre-load these variables, to save time when queried repeatedly
      self.dates = verif.util.clean(self._file.variables["Date"])
      self.offsets = verif.util.clean(self._file.variables["Offset"])
      self.thresholds = self._get_thresholds()
      self.quantiles = self._get_quantiles()
      self.locations = self._get_locations()
      self.variable = self._get_variable()

   @staticmethod
   def is_valid(filename):
      """ Checks that 'filename' is a valid object of this type """
      valid = False
      try:
         file = netcdf(filename, 'r')
         if hasattr(file, "Convensions") and file.Convension == "comps":
            valid = True
         # TODO: Check for dimensions and variables
         file.close()
         return True
      except:
         return False

   @property
   def obs(self):
      return verif.util.clean(self._file.variables["obs"])

   @property
   def deterministic(self):
      return verif.util.clean(self._file.variables["fcst"])

   @property
   def threshold_scores(self):
      thresholds = self.thresholds
      Nt = len(thresholds)
      values = None

      for t in range(0, Nt):
         p_var = self._verif_to_comps_threshold(thresholds[t])
         np.array([Nt], float)
         temp = self._get_score(p_var)
         if values is None:
            shape = [i for i in temp.shape] + [Nt]
            values = np.zeros(shape, float)
         values[:, :, :, t] = temp

      return values

   @property
   def quantile_scores(self):
      quantiles = self.quantiles
      Nq = len(quantiles)
      values = None

      for q in range(0, Nq):
         q_var = self._verif_to_comps_quantile(quantiles[q])
         np.array([Nq], float)
         temp = self._get_score(q_var)
         if values is None:
            shape = [i for i in temp.shape] + [Nq]
            values = np.zeros(shape, float)
         values[:, :, :, q] = temp

      return values

   def _get_locations(self):
      lat = verif.util.clean(self._file.variables["Lat"])
      lon = verif.util.clean(self._file.variables["Lon"])
      id = verif.util.clean(self._file.variables["Location"])
      elev = verif.util.clean(self._file.variables["Elev"])
      locations = list()
      for i in range(0, lat.shape[0]):
         location = verif.location.Location(id[i], lat[i], lon[i], elev[i])
         locations.append(location)
      return locations

   def _get_thresholds(self):
      thresholds = list()
      for (var, v) in self._file.variables.iteritems():
         if(var not in self._dimensionNames):
            threshold = self._comps_to_verif_threshold(var)
            if threshold is not None:
               thresholds.append(threshold)
      return np.array(thresholds)

   def _get_quantiles(self):
      quantiles = list()
      for (var, v) in self._file.variables.iteritems():
         if(var not in self._dimensionNames):
            quantile = self._comps_to_verif_quantile(var)
            if(quantile is not None):
               quantiles.append(quantile)
      return quantiles

   def _get_variable(self):
      name = self._file.Variable
      units = "No units"
      if(hasattr(self._file, "Units")):
         if(self._file.Units == ""):
            units = "No units"
         elif(self._file.Units == "%"):
            units = "%"
         else:
            units = "$" + self._file.Units + "$"
      return verif.variable.Variable(name, units)

   def _get_score(self, metric):
      temp = verif.util.clean(self._file.variables[metric])
      return temp

   @staticmethod
   def _comps_to_verif_threshold(variable_name):
      """ Converts from COMPS name (i.e p03) to verif threshold (i.e 0.3) """
      threshold = None
      if len(variable_name) >= 2 or variable_name[0] == "p":
         variable_name = variable_name.replace("m", "-")
         variable_name = variable_name.replace("p0", "0.")
         variable_name = variable_name.replace("p", "")
         assert(len(np.where(variable_name == ".")) < 2)
         if verif.util.is_number(variable_name):
            threshold = float(variable_name)
      return threshold

   @staticmethod
   def _comps_to_verif_quantile(variable_name):
      """ Converts from COMPS name (i.e q30) to verif quantile (i.e 0.3) """
      quantile = None
      if len(variable_name) >= 2 or variable_name[0] == "q":
         variable_name = variable_name.replace("q0", "0.")
         variable_name = variable_name.replace("q", "")
         if verif.util.is_number(variable_name):
            temp = float(variable_name)/100
            if temp >= 0 and temp <= 1:
               quantile = temp
      return quantile

   @staticmethod
   def _verif_to_comps_threshold(threshold):
      """ Converts from verif threshold (i.e. 0.3) to COMPS name (i.e p03) """
      if threshold == 0:
         variable_name = "0"
      elif np.abs(threshold) < 1:
         variable_name = "%g" % threshold
         variable_name = variable_name.replace(".", "")
      else:
         variable_name = "%d" % threshold
      variable_name = variable_name.replace("-", "m")
      variable_name = "p%s" % variable_name
      return variable_name

   @staticmethod
   def _verif_to_comps_quantile(quantile):
      """ Converts from verif quantile (i.e. 0.3) to COMPS name (i.e q30) """
      if quantile < 0 or quantile > 1:
         return None
      if quantile == 0:
         variable_name = "0"
      else:
         variable_name = "%g" % (quantile * 100)
         variable_name = variable_name.replace(".", "")
      variable_name = "q%s" % variable_name
      return variable_name


class NetcdfCf(Input):
   """
   New standard format, based on NetCDF/CF
   """
   def __init__(self, filename):
      self.fullname = filename
      self._filename = os.path.expanduser(filename)
      self._file = netcdf(self._filename, 'r')
      self.dates = self._get_dates()
      self.offsets = self._get_offsets()
      self.locations = self._get_locations()
      self.thresholds = self._get_thresholds()
      self.quantiles = self._get_quantiles()
      self.variable = self._get_variable()

   @staticmethod
   def is_valid(filename):
      try:
         file = netcdf(filename, 'r')
      except:
         return False
      valid = False
      if(hasattr(file, "Conventions") and file.Conventions == "verif_1.0.0"):
         valid = True
      file.close()
      return valid

   @property
   def obs(self):
      return verif.util.clean(self._file.variables["obs"])

   @property
   def deterministic(self):
      return verif.util.clean(self._file.variables["fcst"])

   @property
   def ensemble(self):
      return verif.util.clean(self._file.variables["ens"])

   @property
   def threshold_scores(self):
      return verif.util.clean(self._file.variables["cdf"])

   @property
   def quantile_scores(self):
      return verif.util.clean(self._file.variables["x"])

   def _get_dates(self):
      return verif.util.clean(self._file.variables["date"])

   def _get_locations(self):
      lat = verif.util.clean(self._file.variables["lat"])
      lon = verif.util.clean(self._file.variables["lon"])
      id = verif.util.clean(self._file.variables["id"])
      elev = verif.util.clean(self._file.variables["elev"])
      locations = list()
      for i in range(0, lat.shape[0]):
         location = verif.location.Location(id[i], lat[i], lon[i], elev[i])
         locations.append(location)
      return locations

   def _get_offsets(self):
      return verif.util.clean(self._file.variables["offset"])

   def _get_thresholds(self):
      return verif.util.clean(self._file.variables["thresholds"])

   def _get_quantiles(self):
      return verif.util.clean(self._file.variables["quantiles"])

   def _get_variable(self):
      name = self._file.standard_name
      units = "No units"
      if(hasattr(self._file, "Units")):
         if(self._file.Units == ""):
            units = "No units"
         elif(self._file.Units == "%"):
            units = "%"
         else:
            units = "$" + self._file.Units + "$"
      return verif.variable.Variable(name, units)


# Flat text file format
class Text(Input):
   description = verif.util.format_argument("text", "Data organized in rows and columns with space as a delimiter. Each row represents one forecast/obs pair, and each column represents one attribute of the data. Here is an example:") + "\n"\
   + verif.util.format_argument("", "") + "\n"\
   + verif.util.format_argument("", "# variable: Temperature") + "\n"\
   + verif.util.format_argument("", "# units: $^oC$") + "\n"\
   + verif.util.format_argument("", "date     offset id      lat     lon      elev obs fcst      p10") + "\n"\
   + verif.util.format_argument("", "20150101 0      214     49.2    -122.1   92 3.4 2.1     0.91") + "\n"\
   + verif.util.format_argument("", "20150101 1      214     49.2    -122.1   92 4.7 4.2      0.85") + "\n"\
   + verif.util.format_argument("", "20150101 0      180     50.3    -120.3   150 0.2 -1.2 0.99") + "\n"\
   + verif.util.format_argument("", "") + "\n"\
   + verif.util.format_argument("", " Any lines starting with '#' can be metadata (currently variable: and units: are recognized). After that is a header line that must describe the data columns below. The following attributes are recognized: date (in YYYYMMDD), offset (in hours), id (location identifier), lat (in degrees), lon (in degrees), obs (observations), fcst (deterministic forecast), p<number> (cumulative probability at a threshold of 10). obs and fcst are required columns: a value of 0 is used for any missing column. The columns can be in any order. If 'id' is not provided, then they are assigned sequentially starting at 0. If there is conflicting information (for example different lat/lon/elev for the same id), then the information from the first row containing id will be used.")

   def __init__(self, filename):
      self.fullname = filename
      self._filename = os.path.expanduser(filename)
      file = open(self._filename, 'rU')
      self._units = "Unknown units"
      self._variable = "Unknown"
      self._pit = None

      self._dates = set()
      self._offsets = set()
      self._locations = set()
      self._quantiles = set()
      self._thresholds = set()
      fields = dict()
      obs = dict()
      fcst = dict()
      cdf = dict()
      pit = dict()
      x = dict()
      indices = dict()
      header = None

      # Default values if columns not available
      offset = 0
      date = 0
      lat = 0
      lon = 0
      elev = 0
      # Store location data, to ensure we don't have conflicting lat/lon/elev info for the same ids
      locationInfo = dict()
      shownConflictingWarning = False

      import time
      start = time.time()
      # Read the data into dictionary with (date,offset,lat,lon,elev) as key and obs/fcst as values
      for rowstr in file:
         if(rowstr[0] == "#"):
            curr = rowstr[1:]
            curr = curr.split()
            if(curr[0] == "variable:"):
               self._variable = ' '.join(curr[1:])
            elif(curr[0] == "units:"):
               self._units = curr[1]
            else:
               verif.util.warning("Ignoring line '" + rowstr.strip() + "' in file '" + self._filename + "'")
         else:
            row = rowstr.split()
            if(header is None):
               # Parse the header so we know what each column represents
               header = row
               for i in range(0, len(header)):
                  att = header[i]
                  if(att == "date"):
                     indices["date"] = i
                  elif(att == "offset"):
                     indices["offset"] = i
                  elif(att == "lat"):
                     indices["lat"] = i
                  elif(att == "lon"):
                     indices["lon"] = i
                  elif(att == "elev"):
                     indices["elev"] = i
                  elif(att == "obs"):
                     indices["obs"] = i
                  elif(att == "fcst"):
                     indices["fcst"] = i
                  else:
                     indices[att] = i

               # Ensure we have required columns
               requiredColumns = ["obs", "fcst"]
               for col in requiredColumns:
                  if(col not in indices):
                     msg = "Could not parse %s: Missing column '%s'" % (self._filename, col)
                     verif.util.error(msg)
            else:
               if(len(row) is not len(header)):
                  verif.util.error("Incorrect number of columns (expecting %d) in row '%s'"
                        % (len(header), rowstr.strip()))
               if("date" in indices):
                  date = self._clean(row[indices["date"]])
               self._dates.add(date)
               if("offset" in indices):
                  offset = self._clean(row[indices["offset"]])
               self._offsets.add(offset)
               if("id" in indices):
                  id = self._clean(row[indices["id"]])
               else:
                  id = np.nan

               # Lookup previous locationInfo
               currLat = np.nan
               currLon = np.nan
               currElev = np.nan
               if("lat" in indices):
                  currLat = self._clean(row[indices["lat"]])
               if("lon" in indices):
                  currLon = self._clean(row[indices["lon"]])
               if("elev" in indices):
                  currElev = self._clean(row[indices["elev"]])
               if not np.isnan(id) and id in locationInfo:
                  lat = locationInfo[id].lat
                  lon = locationInfo[id].lon
                  elev = locationInfo[id].elev
                  if not shownConflictingWarning:
                     if (not np.isnan(currLat) and abs(currLat - lat) > 0.0001) or (not np.isnan(currLon) and abs(currLon - lon) > 0.0001) or (not np.isnan(currElev) and abs(currElev - elev) > 0.001):
                        print currLat - lat, currLon - lon, currElev - elev
                        verif.util.warning("Conflicting lat/lon/elev information: (%f,%f,%f) does not match (%f,%f,%f)" % (currLat, currLon, currElev, lat, lon, elev))
                        shownConflictingWarning = True
               else:
                  if np.isnan(currLat):
                     currLat = 0
                  if np.isnan(currLon):
                     currLon = 0
                  if np.isnan(currElev):
                     currElev = 0
                  location = verif.location.Location(id, currLat, currLon, currElev)
                  self._locations.add(location)
                  locationInfo[id] = location

               lat = locationInfo[id].lat
               lon = locationInfo[id].lon
               elev = locationInfo[id].elev
               key = (date, offset, lat, lon, elev)
               obs[key] = self._clean(row[indices["obs"]])
               fcst[key] = self._clean(row[indices["fcst"]])
               quantileFields = self._get_quantile_fields(header)
               thresholdFields = self._get_threshold_fields(header)
               if "pit" in indices:
                  pit[key] = self._clean(row[indices["pit"]])
               for field in quantileFields:
                  quantile = float(field[1:])
                  self._quantiles.add(quantile)
                  key = (date, offset, lat, lon, elev, quantile)
                  x[key] = self._clean(row[indices[field]])
               for field in thresholdFields:
                  threshold = float(field[1:])
                  self._thresholds.add(threshold)
                  key = (date, offset, lat, lon, elev, threshold)
                  cdf[key] = self._clean(row[indices[field]])

      end = time.time()
      file.close()
      self._dates = list(self._dates)
      self._offsets = list(self._offsets)
      self._locations = list(self._locations)
      self._quantiles = list(self._quantiles)
      self._thresholds = list(self._thresholds)
      Ndates = len(self._dates)
      Noffsets = len(self._offsets)
      Nlocations = len(self._locations)
      Nquantiles = len(self._quantiles)
      Nthresholds = len(self._thresholds)

      # Put the dictionary data into a regular 3D array
      self.obs = np.zeros([Ndates, Noffsets, Nlocations], 'float') * np.nan
      self.deterministic = np.zeros([Ndates, Noffsets, Nlocations], 'float') * np.nan
      if(len(pit) != 0):
         self._pit = np.zeros([Ndates, Noffsets, Nlocations], 'float') * np.nan
      self.threshold_scores = np.zeros([Ndates, Noffsets, Nlocations, Nthresholds], 'float') * np.nan
      self.quantile_scores = np.zeros([Ndates, Noffsets, Nlocations, Nquantiles], 'float') * np.nan
      for d in range(0, Ndates):
         date = self._dates[d]
         end = time.time()
         for o in range(0, len(self._offsets)):
            offset = self._offsets[o]
            for s in range(0, len(self._locations)):
               location = self._locations[s]
               lat = location.lat
               lon = location.lon
               elev = location.elev
               key = (date, offset, lat, lon, elev)
               if(key in obs):
                  self.obs[d][o][s] = obs[key]
               if(key in fcst):
                  self.deterministic[d][o][s] = fcst[key]
               if(key in pit):
                  self._pit[d][o][s] = pit[key]
               for q in range(0, len(self._quantiles)):
                  quantile = self._quantiles[q]
                  key = (date, offset, lat, lon, elev, quantile)
                  if(key in x):
                     self.quantile_scores[d, o, s, q] = x[key]
               for t in range(0, len(self._thresholds)):
                  threshold = self._thresholds[t]
                  key = (date, offset, lat, lon, elev, threshold)
                  if(key in cdf):
                     self.threshold_scores[d, o, s, t] = cdf[key]
      end = time.time()
      maxLocationId = np.nan
      for location in self._locations:
         if(np.isnan(maxLocationId)):
            maxLocationId = location.id
         elif(location.id > maxLocationId):
            maxLocationId = location.id

      counter = 0
      if(not np.isnan(maxLocationId)):
         counter = maxLocationId + 1

      for location in self._locations:
         if(np.isnan(location.id)):
            location.id = counter
            counter = counter + 1

      self.dates = np.array(self._dates)
      self.offsets = np.array(self._offsets)
      self.thresholds = np.array(self._thresholds)
      self.quantiles = np.array(self._quantiles)
      self.locations = self._locations
      self.variable = self._get_variable()

   @staticmethod
   def is_valid(filename):
      return True

   def _get_variable(self):
      return verif.variable.Variable(self._variable, self._units)

   # Parse string into float, changing -999 into np.nan
   def _clean(self, value):
      fvalue = float(value)
      if(fvalue == -999):
         fvalue = np.nan
      return fvalue

   def _get_quantile_fields(self, fields):
      quantiles = list()
      for att in fields:
         if(att[0] == "q"):
            quantiles.append(att)
      return quantiles

   def _get_threshold_fields(self, fields):
      thresholds = list()
      for att in fields:
         if(att[0] == "p" and att != "pit"):
            thresholds.append(att)
      return thresholds


class Fake(Input):
   def __init__(self, obs, fcst):
      self._obs = obs
      self._fcst = fcst
      self.fullname = "Fake"
      self.name = "Fake"

   def get_obs(self):
      return self._obs

   def get_mean(self):
      return self._fcst