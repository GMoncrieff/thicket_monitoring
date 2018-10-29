
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

#list all sentinel 2 level 2 files
ndvi <- list.files("~/data/s2",pattern='\\.tif$', recursive =TRUE, full.names= TRUE)

#format filenames to extract the date of each image
ndvi_date <- data.frame(ndvi) %>%
    separate(ndvi,into = c("ignore1","date","ext"), sep="_",remove = FALSE) %>%
    mutate(date = str_remove(date, "im/")) %>%
    separate(date,into = c("date","rem"), sep="T",remove = TRUE) %>%
    mutate(date=as.Date(date,format= "%Y%m%d")) %>%
    arrange(date) %>% 
    group_by(date) %>% 
    filter(row_number() == 1)

#create dates and names vector
ndvi <- as.character(ndvi_date$ndvi)
dates <- ndvi_date$date

#stack clean data
ndvi_all <- brick(stack(ndvi))
#plot(ndvi_all,4)

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
left<-extent(431022,431778.1,6272878,6274037)
right<-extent(434032.1,434677 ,6270925,6272269)
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

bfm <- bfmSpatial_xreg(ndvi_allm, dates = dates, xreg = av_cell, start=c(2018, 1), history = 'all')
#run monitoring for one pixel
#bfmp <- bfmPixel_xreg(ndvi_all, xreg = av_cell, dates = dates, cell = 114695, start=c(2018, 1), history = 'all',plot = TRUE)


# change mapping ----------------------------------------------------------

#change detected
change <- raster(bfm, 1)
#magnitude of change
magn <- raster(bfm, 2)
#magnitude threshold - manually tuned
magn[magn > -0.12] <- NA
# make a version showing only breakpoing pixels
magn_bkp <- magn
magn_bkp[is.na(change)] <- NA
#plot(magn_bkp)

#sieve out noise  - manually tuned
magn9_sieve <- areaSieve(magn_bkp, thresh=900)
#plot(magn9_sieve)

#create raster with day of detection as values
change_day<-mask(change,magn9_sieve)
change_day<-(change_day-2018)*365

writeRaster(change_day,file='sent_breakday.tiff',overwrite=TRUE)
