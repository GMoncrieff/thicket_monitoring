import fnmatch
import os
import shutil
import zipfile
import subprocess
from osgeo import gdal
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import rasterio as rio
import numpy as np
# connect to the API
from sentinelsat import SentinelAPI, read_geojson, geojson_to_wkt
from datetime import date


#to find raw files after they are downloaded
import fnmatch
def find(pattern, path):
    result = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                result.append(os.path.join(root, name))
    return result


def calc_ndvi(red,nir,udm_file,filename):
    
    #filename
    fname = "OUTPUT LOCATION" + filename + '_ndvi.tif'
    pname = "OUTPUT LOCATION" + filename + '_ndvi.png'
    
    #load usabel data mask
    with rio.open(udm_file) as src:
        band_udm = src.read(1)
    # Load red and NIR bands 
    with rio.open(red) as src:
        band_red = src.read(1)
    with rio.open(nir) as src:
        band_nir = src.read(1)

    #create 0/1 mask
    #soil
    band_udm[band_udm==5] = 200
    #vegetation
    band_udm[band_udm==4] = 200
    band_mask = band_udm==200

    # Allow division by zero
    np.seterr(divide='ignore', invalid='ignore')

    # Calculate NDVI
    ndvi = (band_nir.astype(float) - band_red.astype(float)) / (band_nir + band_red)
    #mask
    ndvi = ndvi * band_mask
    ndvi[ndvi==0]=np.nan

    # Set spatial characteristics of the output object to mirror the input
    kwargs = src.meta
    kwargs.update(
        dtype=rio.float64,
        count = 1)

    #save geotif
    with rio.open(fname, 'w', **kwargs) as dst:
            dst.write_band(1, ndvi.astype(rio.float64))
    #save image       
    plt.imsave(pname, ndvi, cmap=plt.cm.brg)

os.environ['SENTINEL_USER'] = "username"
os.environ['SENTINEL_PASSWORD'] = "password"
os.environ['SEN2COR_HOME '] = "install_directory of sen2cor"
os.chdir('OUTPUT DIR')
pathcmd = 'export PATH=$PATH:Sen2Cor-02.05.05-Linux64/bin'
os.system(pathcmd)

#full time period for data dowlnload
START = '20150501'
END = '20181029'

#call sentinel api
api = SentinelAPI('username', 'password', 'https://scihub.copernicus.eu/dhus')

# search by polygon, time, and SciHub query keywords
footprint = geojson_to_wkt(read_geojson('data/alex_sample.geojson'))

products = api.query(footprint,
                     date=(START, END),
                     platformname='Sentinel-2')

# download all results from the search
#api.download_all(products)

#or download one by one
for key, value in products.items():
    
    filetemp = value['title']
    filename = filetemp.split('_')[2]
    print(filetemp)
    #download file
    print('downloading ' + filename)
    api.download(key)
    
    #unzip download
    filezip = value['title'] + '.zip'
    zip_ref = zipfile.ZipFile(filezip, 'r')
    zip_ref.extractall()
    zip_ref.close()
    
    #create L2A command to turn L1 data to L2
    file = value['title'] + '.SAFE'
    cmd = 'Sen2Cor-02.05.05-Linux64/bin/L2A_Process ' + os.getcwd() + '/' + file    
    print('Processing ' + filename)
    os.system(cmd)
    
    #rm zip file of raw data
    rmzip = 'rm -r -f ' + filezip
    os.system(rmzip)
    #rm L1 data
    rml1 = 'rm -r -f ' + file
    os.system(rml1)
    
    #locate L2 files needed for NDVI 
    s2dir = fnmatch.filter(os.listdir(), '*.SAFE')[0]
    r_file = find('*_B02_10m.jp2', s2dir)[0]
    nir_file = find('*_B08_10m.jp2', s2dir)[0]
    udm_file = find('*_SCL_20m.jp2', s2dir)[0]
    
    #open files, and clip to area of interest
    #projwin and outputBounds manually calculated for AOI
    
    #first we crop the data
    print("translating")
    os.mkdir('temp')
    
    ds_nir = gdal.Open(nir_file)
    gdal.Translate('temp/sentinel_output_nir.tif', ds_nir, format = "GTiff", projWin = [430922.3, 6274140, 434738.86, 6270833.12])
    ds_nir = None
    
    ds_r = gdal.Open(r_file)
    gdal.Translate('temp/sentinel_output_r.tif', ds_r, format = "GTiff", projWin = [430922.3, 6274140, 434738.86, 6270833.12])
    ds_r = None
    
    ds_mask = gdal.Open(udm_file)
    gdal.Translate('temp/sentinel_output_udm.tif', ds_mask, format = "GTiff", projWin = [430922.3, 6274160, 434738.86, 6270833.12])
    ds_mask = None
    
    #then we align all the rasters
    print("warping")
    ds_nir = gdal.Open('temp/sentinel_output_nir.tif')
    nirfile = 'temp/sentinel_output_nir2.tif'
    gdal.Warp(nirfile, ds_nir, format = "GTiff", xRes = 10, yRes =10, outputBounds = [430922.3, 6270833.12, 434738.86, 6274140])
    ds_nir = None
    
    ds_r = gdal.Open('temp/sentinel_output_r.tif')
    rfile = 'temp/sentinel_output_r2.tif'
    gdal.Warp(rfile, ds_r, format = "GTiff", xRes = 10, yRes =10, outputBounds = [430922.3, 6270833.12, 434738.86, 6274140])
    ds_r = None
    
    ds_mask = gdal.Open('temp/sentinel_output_udm.tif')
    udmfile = 'temp/sentinel_output_udm2.tif'
    gdal.Warp(udmfile, ds_mask, format = "GTiff", xRes = 10, yRes =10,  outputBounds = [430922.3, 6270833.12, 434738.86, 6274140],dstNodata=99)
    ds_mask = None
    
    #now we calc ndvi and save output
    print("calculating ndvi")
    calc_ndvi(rfile,nirfile,udmfile,filename)
    
    #rm temp files
    rmtemp = 'rm -r -f temp'
    os.system(rmtemp)
    #rm L2 files
    rml2 = 'rm -r -f ' + s2dir
    os.system(rml2)
    print("finished ")

