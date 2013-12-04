# Name:         mapper_globcolour_l3m
# Purpose:      Mapping for L3 mapped GLOBCOLOUR data
# Authors:      Anton Korosov
# Licence:      This file is part of NANSAT. You can redistribute it or modify
#               under the terms of GNU General Public License, v.3
#               http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import os.path
import glob

import gdal

import numpy as np

from vrt import VRT, GeolocationArray
from globcolour import Globcolour


class Mapper(VRT, Globcolour):
    ''' Mapper for GLOBCOLOR L3M products'''

    def __init__(self, fileName, gdalDataset, gdalMetadata, **kwargs):
        ''' GLOBCOLOR L3M VRT '''

        print "=>%s<=" % gdalMetadata['NC_GLOBAL#title']

        if 'GlobColour' not in gdalMetadata['NC_GLOBAL#title']:
            raise AttributeError("GlobColour BAD MAPPER")

        # get list of similar (same date) files in the directory
        iDir, iFile = os.path.split(fileName)
        iFileName, iFileExt = os.path.splitext(iFile)
        print 'idir:', iDir, iFile, iFileName[0:30], iFileExt[0:8]

        simFilesMask = os.path.join(iDir, iFileName[0:30] + '*')
        simFiles = glob.glob(simFilesMask)
        print 'simFilesMask, simFiles', simFilesMask, simFiles

        metaDict = []
        for simFile in simFiles:
            print 'simFile', simFile
            # open file, get metadata and get parameter name
            simSupDataset = gdal.Open(simFile)
            simSubDatasets = simSupDataset.GetSubDatasets()
            simWKV = None
            for simSubDataset in simSubDatasets:
                if '_mean' in simSubDataset[0]:
                    simValidSupDataset = simSupDataset
                    simGdalDataset = gdal.Open(simSubDataset[0])
                    simBand = simGdalDataset.GetRasterBand(1)
                    simBandMetadata = simBand.GetMetadata()
                    simVarname = simBandMetadata['NETCDF_VARNAME']
                    # get WKV
                    print '    simVarname', simVarname
                    if simVarname in self.varname2wkv:
                        simWKV = self.varname2wkv[simVarname]
                        break

            # skipp adding this similar file if it is not valid
            if simWKV is None:
                continue

            metaEntry = {
                'src': {'SourceFilename': simSubDataset[0],
                        'SourceBand':  1},
                'dst': {'wkv': simWKV, 'original_name': simVarname}}

            # add wavelength and name
            longName = simBandMetadata['long_name']
            if 'Fully normalised water leaving radiance' in longName:
                simWavelength = simVarname.split('L')[1].split('_mean')[0]
                metaEntry['dst']['suffix'] = simWavelength
                metaEntry['dst']['wavelength'] = simWavelength

            # add band with rrsw
            metaEntry2 = None
            if simWKV == 'surface_upwelling_spectral_radiance_in_air_emerging_from_sea_water':
                solarIrradiance = simBandMetadata['solar_irradiance']
                metaEntry2 = {'src': metaEntry['src']}
                metaEntry2['dst'] = {'wkv': 'surface_ratio_of_upwelling_radiance_emerging_from_sea_water_to_downwelling_radiative_flux_in_water',
                                     'suffix': simWavelength,
                                     'wavelength': simWavelength,
                                     #'expression': 'self["nLw_%s"] / %s / (0.52 + 1.7 * self["nLw_%s"] / %s)' % (simWavelength, solarIrradiance, simWavelength, solarIrradiance),
                                     'expression': 'self["nLw_%s"] / %s' %
                                     (simWavelength, solarIrradiance)
                                     }

            print '        metaEntry', metaEntry
            metaDict.append(metaEntry)
            if metaEntry2 is not None:
                print '        metaEntry2', metaEntry2
                metaDict.append(metaEntry2)

        print 'simSubDatasets', simValidSupDataset.GetSubDatasets()
        for simSubDataset in simValidSupDataset.GetSubDatasets():
            print 'simSubDataset', simSubDataset
            if '_flags ' in simSubDataset[1]:
                print '    mask simSubDataset', simSubDataset[1]
                flags = gdal.Open(simSubDataset[0]).ReadAsArray()
                mask = np.ones(flags.shape) * 64
                mask[np.bitwise_and(flags, np.power(2, 0)) > 0] = 1
                mask[np.bitwise_and(flags, np.power(2, 3)) > 0] = 2

        self.sub_maskVRT = VRT(array=mask)

        metaDict.append(
            {'src': {'SourceFilename': self.sub_maskVRT.fileName, 'SourceBand': 1},
             'dst': {'name': 'mask'}})

        # create empty VRT dataset with geolocation only
        simGdalDataset.SetProjection('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.01745329251994328,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]')
        VRT.__init__(self, simGdalDataset)

        # add bands with metadata and corresponding values to the empty VRT
        self._create_bands(metaDict)

        # Add valid time
        #startYear = int(gdalMetadata['Start Year'])
        #startDay = int(gdalMetadata['Start Day'])
        #self._set_time(datetime.datetime(startYear, 1, 1) + datetime.timedelta(startDay))
        #"""
