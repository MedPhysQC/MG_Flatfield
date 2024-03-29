#!/usr/bin/env python
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# This code is an analysis module for WAD-QC 2.0: a server for automated 
# analysis of medical images for quality control.
#
# The WAD-QC Software can be found on 
# https://bitbucket.org/MedPhysNL/wadqc/wiki/Home
# 
#
# Changelog:
#   20231108: fix for small clustersize giving negative ellipse size; added thumbnail of normal; added Cu filter
#   20230906: remove deprecated warning; Pillow 10.0.0
#   20220118: added dc_offset parameter (KvG/AS)
#   20200508: dropping support for python2; dropping support for WAD-QC 1; toimage no longer exists in scipy.misc
#   20200401: made some dicom values floats
#   20190426: Fix for matplotlib>3
#   20161220: added artefact border setting param; removed class variables; removed class variables
#   20160802: sync with pywad1.0
#   20160622: removed adding limits (now part of analyzer)
#   20160620: remove quantity and units
#
# ./QCMammo_wadwrapper.py -c Config/mg_hologic_selenia_series.json -d TestSet/StudySelenia -r results_selenia.json

__version__ = '20231108'
__author__ = 'aschilham'

import os
# this will fail unless wad_qc is already installed
from wad_qc.module import pyWADinput
from wad_qc.modulelibs import wadwrapper_lib

if not 'MPLCONFIGDIR' in os.environ:
    try:
        # new method
        from importlib.metadata import version as pkg_version
    except:
        # deprecated method
        import pkg_resources
        def pkg_version(what):
            return pkg_resources.get_distribution(what).version
    try:
        #only for matplotlib < 3 should we use the tmp work around, but it should be applied before importing matplotlib
        matplotlib_version = [int(v) for v in pkg_version("matplotlib").split('.')]
        if matplotlib_version[0]<3:
            os.environ['MPLCONFIGDIR'] = "/tmp/.matplotlib" # if this folder already exists it must be accessible by the owner of WAD_Processor 
    except:
        os.environ['MPLCONFIGDIR'] = "/tmp/.matplotlib" # if this folder already exists it must be accessible by the owner of WAD_Processor 

import matplotlib
matplotlib.use('Agg') # Force matplotlib to not use any Xwindows backend.

try:
    import pydicom as dicom
except ImportError:
    import dicom
import QCMammo_lib

def logTag():
    return "[QCMammo_wadwrapper] "

# MODULE EXPECTS PYQTGRAPH DATA: X AND Y ARE TRANSPOSED!

def _setRunParams(cs, params):
    # Use the params in the config file 
    try:
        # a name for identification
        # art_borderpx_lrtb = "0;0;12;12" # skip this number of pixels in artefact evaluation for left, right, top, bottom
        art_borderpx_lrtb = params['art_borderpx_lrtb']
    except:
        art_borderpx_lrtb = "0;0;0;0"

    try:
        art_borderpx_lrtb = [int(x) for x in art_borderpx_lrtb.split(';')]
            
    except Exception as e:
        raise ValueError(logTag()+" Malformed parameter definition!"+str(e))

    cs.art_borderpx_lrtb = art_borderpx_lrtb

    try:
        dc_offset = int(params['dc_offset'])
    except:
        dc_offset = 0	
    cs.dc_offset = dc_offset

##### Series wrappers
def qc_series(data, results, action):
    """
    QCMammo_UMCU checks:
        Uniformity (5 rois) and SNR (hologic),
        DoseRatio (empirical/calculated from DICOM)
        Artefacts (spots, dead pixels)

    Workflow:
        2. Check data format
        3. Build and populate qcstructure
        4. Run tests
        5. Build xml output
        6. Build artefact picture thumbnail
    """
    try:
        params = action['params']
    except KeyError:
        params = {}

    inputfile = data.series_filelist[0]  # give me a filename

    ## 2. Check data format
    dcmInfile,pixeldataIn,dicomMode = wadwrapper_lib.prepareInput(inputfile, headers_only=False, logTag=logTag())

    ## 3. Build and populate qcstructure
    remark = ""
    qcmammolib = QCMammo_lib.Mammo_QC()
    cs_mam = QCMammo_lib.MammoStruct(dcmInfile,pixeldataIn)
    cs_mam.verbose = False # do not produce detailed logging
    _setRunParams(cs_mam, params)
    
    if qcmammolib.NeedsCropping(cs_mam):
        cs_mam.expertmode = True
        qcmammolib.RestrictROI(cs_mam)
        remark = "CROPPED"

    ## 4. Run tests
    # Uniformity check
    error = qcmammolib.Uniformity(cs_mam)
    if error:
        remark += "/ERROR_UNIFORMITY"
    # Contrast L50
    error = qcmammolib.L50Contrast(cs_mam) # doesn't do anything if not L50
    if error:
        remark += "/ERROR_L50CONTRAST"
    # Dose Ratio
    error = qcmammolib.DoseRatio(cs_mam)
    if error:
        remark += "/ERROR_DOSERATIO"
    # Artefacts
    error = qcmammolib.Artefacts(cs_mam)
    if error:
        remark += "/ERROR_ARTEFACTS"

    ## 5. Build xml output
    ## Struct now contains all the results and we can write these to the
    ## WAD IQ database
    includedlist = [
        'unif_pct',
        'snr_hol',
        'doseratio',
        'art_clusters',
        'expert_inoutoverin',
        'contrast_snr'
    ]
    excludedlist = [
        'verbose',
        'dcmInfile',
        'pixeldataIn',
        'hasmadeplots',
        'means',
        'stdevs',
        'unif',
        'snr_hol',
        'unif_rois',
        'doseratio',
        'art_clusters',
        'art_image',
        'art_borderpx',
        'art_threshold',
        'art_rois',
        'expertmode',
        'expert_roipts',
        'expert_frac',
        'expert_inoutoverin',
        'filtername',
        'scannername',
        'contrast_rois',
        'contrast_mean',
        'contrast_sd'
    ]

    
    varname = 'NOTE'
    results.addString(varname, remark)

    for elem in cs_mam.__dict__:
        if elem in includedlist:
            newkeys = []
            newvals = []
            try:
                elemval =  cs_mam.__dict__[elem]
                if 'contrast_snr' in elem: # array
                    for ix,snr in enumerate(elemval):
                        newkeys.append('CNR'+str(ix))
                        newvals.append(snr)
                elif 'art_clusters' in elem:
                    newkeys.append(str(elem))
                    newvals.append(len(elemval))
                else:
                    newkeys.append(str(elem))
                    newvals.append(elemval)
            except:
                print(logTag()+"error for",elem)

            tmpdict={}
            for key,val in zip(newkeys,newvals):
                varname = key
                results.addFloat(varname, val)


    ## 6. Build artefact picture thumbnail
    filename = 'test_artefacts.jpg' # Use jpg if a thumbnail is desired

    #object_naam_pad = outputfile.replace('result.xml','test'+idname+'.jpg') # Use jpg if a thumbnail is desired
    qcmammolib.saveAnnotatedImage(cs_mam, filename, 'artefacts')
    varname = 'ArtefactImage'
    results.addObject(varname, filename)

    ## also add uniformity thumbnail
    filename = 'test_uniformity.jpg' # Use jpg if a thumbnail is desired
    qcmammolib.saveAnnotatedImage(cs_mam, filename, 'uniformity')
    varname = 'UniformityImage'
    results.addObject(varname, filename)

def acqdatetime_series(data, results, action):
    """
    Read acqdatetime from dicomheaders and write to IQC database

    Workflow:
        1. Read only headers
    """
    try:
        params = action['params']
    except KeyError:
        params = {}

    ## 1. read only headers
    dcmInfile = dicom.read_file(data.series_filelist[0][0], stop_before_pixels=True)

    dt = wadwrapper_lib.acqdatetime_series(dcmInfile)

    results.addDateTime('AcquisitionDateTime', dt) 

def header_series(data, results, action):
    """
    Read selected dicomfields and write to IQC database

    Workflow:
        1. Run tests
        2. Build xml output
    """
    try:
        params = action['params']
    except KeyError:
        params = {}

    try:
        info = params.find("info").text
    except AttributeError:
        info = 'qc' # selected subset of DICOM headers informative for QC testing

    dcmInfile = dicom.read_file(data.series_filelist[0][0], stop_before_pixels=True)

    ## 1. Run tests
    qcmammolib = QCMammo_lib.Mammo_QC()
    cs = QCMammo_lib.MammoStruct(dcmInfile,None)
    cs.verbose = False # do not produce detailed logging
    _setRunParams(cs, params)
    
    dicominfo = qcmammolib.DICOMInfo(cs,info)
    floatlist = [
        "BodyPartThickness",
        "CompressionForce",
        "DistanceSourceToDetector",
        "DistanceSourceToPatient",
        "EntranceDose_(mGy)",
        "HalfValueLayer_(mm)",
        "OrganDose",
        "kVp",
        "muAs"
    ]
    ## 2. Add results to 'result' object
    varname = 'pluginversion'
    results.addString(varname, str(qcmammolib.qcversion))
    for di in dicominfo:
        varname = di[0]
        if varname in floatlist:
            try:
                results.addFloat(varname, float(di[1]))
            except:
                results.addString(varname, str(di[1])[:min(len(str(di[1])),100)])
        else:
            results.addString(varname, str(di[1])[:min(len(str(di[1])),100)])

if __name__ == "__main__":
    data, results, config = pyWADinput()

    # read runtime parameters for module
    for name,action in config['actions'].items():
        if name == 'acqdatetime':
            acqdatetime_series(data, results, action)

        elif name == 'header_series':
            header_series(data, results, action)
        
        elif name == 'qc_series':
            qc_series(data, results, action)

    #results.limits["minlowhighmax"]["mydynamicresult"] = [1,2,3,4]

    results.write()
