
# load libraries ----------------------------------------------------------

library(raster)
library(stringr)
library(dplyr)
library(tidyr)
library(rgdal)
library(rgeos)
#library(devtools)
#install_github('GMoncrieff/bfastSpatial')
library(bfastSpatial)


# load data ---------------------------------------------------------------


#area of interest for masking
alex <- readOGR(dsn = '~/data/alexcrop','alexcrop')

#list all planet sr files
ndvi <- list.files("~/data/sr",pattern='\\.tif$', recursive =TRUE, full.names= TRUE)

#format filenames to extract the date of each image
ndvi_date <- data.frame(ndvi) %>%
  separate(ndvi,into = c("ig0","date","ig1","ig2","ig3"), sep="_",remove = FALSE) %>%
  mutate(date = str_remove(date, "sp/")) %>%
  mutate(date=as.Date(date,format= "%Y%m%d")) %>%
  arrange(date) %>%
  group_by(date) %>%
  filter(row_number() == 1)

#create dates vector
ndvi <- as.character(ndvi_date$ndvi)
dates <- ndvi_date$date
#create names vector
gdalnm <- paste0(dates,'_pl.tif')

#we need to warp the rasters to have the same extent
for (i in 1:length(ndvi)){
  gdalwarp(ndvi[i],gdalnm[i],
           t_srs='+proj=utm +zone=35 +south +datum=WGS84 +units=m +no_defs +ellps=WGS84 +towgs84=0,0,0',
           tr=c(3,3),
           te=c(430980.2,6270583,434656.1,6273428), #manually chosen extent
           overwrite=TRUE,
           verbose=TRUE)
}


#now redo extraction of dates and filenames for warped and ready files
ndvi <- list.files("/home/glenn",pattern='\\_pl.tif$', full.names= TRUE)
ndvin <- list.files("/home/glenn",pattern='\\_pl.tif$', full.names= FALSE)
ndvi_date <- data.frame(ndvin) %>%
    separate(ndvin,into = c("date","ext"), sep="_",remove = FALSE) %>%
    mutate(date=as.Date(date,format= "%Y-%m-%d")) %>%
    arrange(date) %>% 
    group_by(date) %>% 
    filter(row_number() == 1)

#get dates
ndvi <- as.character(ndvi)
dates <- ndvi_date$date

#stack clean data
ndvi_all <- brick(stack(ndvi))
#plot(ndvi_all,1)


# preprocessed data -------------------------------------------------------

#mask data using a polygon for areas that we are intersted in monitoring
alex<-spTransform(alex,crs(ndvi_all))
alexsp<-crop(alex,extent(ndvi_all))
alexspr <- rasterize(alexsp,ndvi_all,"VEG_ID")
ndvi_allm <- raster::mask(ndvi_all,alexspr)


# regressors --------------------------------------------------------------


#calc averages for areas within reasters that we know are natural
#these will be used as regressors in spatial monitoring

#manually define areas
left<-extent(431022,431778.1,6272878,6273337)
right<-extent(434032.1,434640 ,6270600,6272269)
leftp <- as(left, 'SpatialPolygons')  
rightp <- as(right,'SpatialPolygons')
lr <- raster::bind(leftp,rightp)

#extract only these areas
ndvi_ma <- mask(ndvi_all,lr)

#calc average of entire areas
av_cell <- cellStats(ndvi_ma,stat= 'mean')
av_cell[av_cell == "NaN"] = "NA" 
av_cell<-as.numeric(av_cell)
av_cell <- na.approx(av_cell)


# run monitoring algorithm ------------------------------------------------

bfm <- bfmSpatial_xreg(ndvi_allm, dates = dates, xreg = av_cell, start=c(2018, 1), history = 'all', mc.cores = 32)
#run monitoring for one pixel
#bfmp <- bfmPixel_xreg(ndvi_all, xreg = av_cell, dates = dates, cell = c(431854.9, 6271137), start=c(2018, 1), history = 'all',plot = TRUE)

#save(bfm,file='bfm_planet_sr.RData')


# change mapping ----------------------------------------------------------

#change detected
change <- raster(bfm, 1)
#magnitude of change
magn <- raster(bfm, 2)
#magnitude threshold - manually tuned
magn[magn > -0.22] <- NA
# make a version showing only breakpoing pixels
magn_bkp <- magn
magn_bkp[is.na(change)] <- NA
#plot(magn_bkp)

#sieve out noise  - manually tuned
magn13_sieve <- areaSieve(magn_bkp, thresh=1300)
#plot(magn13_sieve)

#create raster with day of detection as values
change_day<-mask(change,magn13_sieve)
change_day<-(change_day-2018)*365

writeRaster(change_day,file='planet_breakday.tiff',overwrite=TRUE)

#DONE