import rasterio as rio
import matplotlib.pyplot as plt
import requests
import numpy as np
import os
import zipfile
import glob
from xml.dom import minidom

def calc_ndvi(filename,image_file,udm_file,meta_file):
    
    #filename
    fname = "ndvi_sp/" + filename + '_ndvi.tif'
    pname = "ndvi_im/" + filename + '_ndvi.png'
    #load usabel data mask
    with rio.open(udm_file) as src:
        band_udm = src.read(1)
    # Load red and NIR bands - note all PlanetScope 4-band images have band order BGRN
    with rio.open(image_file) as src:
        band_red = src.read(3)
    with rio.open(image_file) as src:
        band_nir = src.read(4)

     #create 0/1 mask
    band_mask = band_udm==0

    # Allow division by zero
    np.seterr(divide='ignore', invalid='ignore')

    # Calculate NDVI
    ndvi = (band_nir.astype(float) - band_red.astype(float)) / (band_nir + band_red)

    ndvi = ndvi * band_mask
    ndvi[ndvi<=0]=np.nan

    # Set spatial characteristics of the output object to mirror the input
    kwargs = src.meta
    kwargs.update(
        dtype=rio.float32,
        count = 1)

    #save geotif
    with rio.open(fname, 'w', **kwargs) as dst:
            dst.write_band(1, ndvi.astype(rio.float32))
    #save image       
    plt.imsave(pname, ndvi, cmap=plt.cm.brg)


#DEF globals
#home dir
os.chdir('HOME DIR')

#Find zipfiles
pl_zips = glob.glob('*.zip')
pl_str = [pl.replace('alex_sample_planet', '') for pl in pl_zips]
pl_str = [pl.replace('.zip', '') for pl in pl_str]
pl_dt = [pl.split("_")[2] for pl in pl_str]

#unzip
for pl in pl_zips:
    zip_ref = zipfile.ZipFile(pl, 'r')
    zip_ref.extractall()
    zip_ref.close()

#names of data and mask files
pl_ras = [pl + '_3B_AnalyticMS_SR_clip.tif' for pl in pl_str]
pl_udm = [pl + '_3B_AnalyticMS_DN_udm_clip.tif' for pl in pl_str]


#loop through files
for filename,image_file,udm_file,meta_file in zip(pl_str,pl_ras,pl_udm,pl_meta):
    calc_ndvi(filename,image_file,udm_file,meta_file)

