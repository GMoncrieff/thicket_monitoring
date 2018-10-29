import json
import os
import requests
import pandas as pd
from datetime import date
from requests.auth import HTTPBasicAuth
from retrying import retry



#DEF globals
#set wd
os.chdir('SET HOME DIR')
#output dir
outdir_tr = 'SET OUTPUT TR DIR'
outdir_val = 'SET OUTPUT VAL DIR'

#API key
os.environ['PL_API_KEY'] = "PLANETAPIKEY"

#activvate session
session = requests.Session()
session.auth = (os.environ['PL_API_KEY'], '')

#read AOI
with open('data/alex_sample.geojson') as f:
    alex_geom = json.load(f)

#training and val date
start_tr = "2017-02-01T00:00:00.000Z"
end_tr = "2017-12-31T00:00:00.000Z"
start_val = "2018-01-01T00:00:00.000Z"
end_val = "2018-03-01T00:00:00.000Z"


#extract data from search page response
def handle_page(page):
    
    ids = []
    use = []
    dates = []
    
    for item in page["features"]:
        
        idt = item["id"]
        uset = item["properties"]['usable_data']
        datest = item["properties"]['acquired']
        ids.append(idt)
        use.append(uset)
        dates.append(datest)
    
    prop = pd.DataFrame(
    {'acquired': dates,
     'id': ids,
     'usable_data': use
    })
    
    return prop

#get search page response
def fetch_page(search_url,proper):
    
    page = session.get(search_url).json()
    prop = handle_page(page)
    proper = pd.concat([proper,prop])
    #print(proper)

    next_url = page["_links"].get("_next")
    if next_url:
        fetch_page(next_url,proper)
    else:
        global properties
        properties = proper

#retry if unsuccess api call
def retry_if_400(result):
    return result.status_code >= 400

#retry if not dowloaded
def retry_dl(result):
    return result == 0

#attempt to activate clip and ship task
@retry(retry_on_result=retry_if_400, stop_max_attempt_number=8, wait_exponential_multiplier=1000, wait_exponential_max=256000)
def activate_item(image_target,item_type,alex_geom):
    print("requesting: " + image_target)

    # request an item
    targets = {
      "item_id": image_target,
      "item_type": item_type,
      "asset_type": "analytic_sr"
    }

    clip_endpoint_request = {
      "aoi": alex_geom,
      "targets": [targets]
    }

    # request activation
    result =       requests.post(
        'https://api.planet.com/compute/ops/clips/v1',
        auth=HTTPBasicAuth(os.environ['PL_API_KEY'], ''),
        json=clip_endpoint_request)
    
    print("request for item sent: " + image_target)
    
    if result.status_code <= 400:
        print("request successful:" + image_target)
    else:
        print("request unsuccessful:" + image_target)
    
    return result

#download activated clip and ship
@retry(retry_on_result=retry_dl,stop_max_delay=1800000,wait_exponential_multiplier=1000, wait_exponential_max=60000)
def download_clip_item(result,image_target,item_type,alex_geom,outdir):
    
    dl_flag = 0
    #api request id
    poll_id = result.json()['id']
    
    #api response
    item = session.get('https://api.planet.com/compute/ops/clips/v1/' + poll_id)
    #name file
    filename = outdir + image_target + '.zip'
    print(item.json()['state'])

    if item.json()['state'] == 'succeeded':
        print("downloading: " + image_target)
        #download link
        link_dl = item.json()['_links']['results']
        #download and write to file
        r = requests.get(link_dl[0])
        with open(filename, 'wb') as f:  
            f.write(r.content)
        
        dl_flag = 1
        
    else:
        print("still running. waiting a bit:" + image_target)
        
    return dl_flag


#create filters
geometry_filter = {
  "type": "GeometryFilter",
  "field_name": "geometry",
  "config": alex_geom
}

# get images acquired within a date range
date_range_filter_tr = {
  "type": "DateRangeFilter",
  "field_name": "acquired",
  "config": {
    "gte": start_tr,
    "lte": end_tr
  }
}

# get images acquired within a date range
date_range_filter_val = {
  "type": "DateRangeFilter",
  "field_name": "acquired",
  "config": {
    "gte": start_val,
    "lte": end_val
  }
}

# only get images which have <20% cloud coverage
cloud_cover_filter = {
  "type": "RangeFilter",
  "field_name": "cloud_cover",
  "config": {
    "lte": 0.60
  }
}

#only get inmages that have a surface reflectance product
sr_filter =  {  
   "type":"PermissionFilter",
   "config":[  
      "assets.analytic_sr:download"
   ]
}
    

#pm_filter = {  
#   "type":"PermissionFilter",
#   "config":[  
#      "assets:download",
#      "assets.visual:download",
#      "assets.analytic:download"
#   ]
#}

# combine our geo, date, cloud filters
combined_filter_tr = {
  "type": "AndFilter",
  "config": [geometry_filter, date_range_filter_tr, cloud_cover_filter,sr_filter]
}

combined_filter_val = {
  "type": "AndFilter",
  "config": [geometry_filter, date_range_filter_val, cloud_cover_filter,sr_filter]
}

item_type = "PSScene4Band"


#search with filters

# API request object
alex_small_model_tr = {
  "name": "alex_small_model_tr",
  "item_types": [item_type],
  "filter": combined_filter_tr
}

# Create a Saved Search
saved_search_tr =     session.post(
        'https://api.planet.com/data/v1/searches/',
        json=alex_small_model_tr)

# API request object
alex_small_model_val = {
  "name": "alex_small_model_val",
  "item_types": [item_type],
  "filter": combined_filter_val
}

# Create a Saved Search
saved_search_val =     session.post(
        'https://api.planet.com/data/v1/searches/',
        json=alex_small_model_val)


# after you create a search, save the id. This is what is needed
# to execute the search.
saved_search_id_tr = saved_search_tr.json()["id"]
saved_search_id_val = saved_search_val.json()["id"]


##TRAINING DATA
#api request url
first_page_tr =     ("https://api.planet.com/data/v1/searches/{}" +
        "/results?_page_size={}").format(saved_search_id_tr, 6)

#template dataframe to populate. results dataframe named 'properties'
proper = pd.DataFrame(
{'acquired': [],
 'id': [],
 'usable_data': []
})

# kick off the pagination of api response
fetch_page(first_page_tr,proper)

# Get top 20 images with most data in the month for training period
properties['acquired'] = pd.to_datetime(properties['acquired'])
properties['YearMonth'] = properties['acquired'].map(lambda x: 100*x.year + x.month)

propdf = properties.sort_values('usable_data',ascending=False).groupby('YearMonth').head(20)
propdf.sort_values('acquired',ascending=True)   

target_list_tr = propdf['id'].tolist()


##VALIDATION DATA
#api request url
first_page_val =     ("https://api.planet.com/data/v1/searches/{}" +
        "/results?_page_size={}").format(saved_search_id_val, 6)

#template dataframe to populate. results dataframe named 'properties'
proper = pd.DataFrame(
{'acquired': [],
 'id': [],
 'usable_data': []
})

# kick off the pagination of api response
fetch_page(first_page_val,proper)

# Get top 2 images with most data each day
properties['acquired'] = pd.to_datetime(properties['acquired'])
properties['YearMonthDay'] = properties['acquired'].map(lambda x: 10000*x.year + 100*x.month + x.day)

propdf = properties.sort_values('usable_data',ascending=False).groupby('YearMonthDay').head(2)
propdf.sort_values('acquired',ascending=True)   

target_list_val = propdf['id'].tolist()


#loop through trainging items and download
print("TRAINING DATA")
for image_target in target_list_tr:
    #attempt to activate
    try:
        print("attempting training activation:" + image_target)
        #tell planet to execute clip and ship
        result = activate_item(image_target,item_type,alex_geom)
        
        #download result of clip and ship
        try:
            print("attempting download:" + image_target)
            dl = download_clip_item(result,image_target,item_type,alex_geom,outdir_tr)
            print("finished: " + image_target)
            print("\n")
            print("\n")
        
        #if cannot download
        except:
            print("download failed: " + image_target)
            print("\n")
            print("\n")
    
    #if cannot activate
    except:
        print("activation failed:" + image_target)
        print("not attempting download:" + image_target)
        print("\n")

print("\n")        
print('COMPLETED TRAINING DATA')
print("\n")


#loop through validation items and download
print("VALIDATION DATA")
for image_target in target_list_val:
    #attempt to activate
    try:
        print("attempting validation activation:" + image_target)
        #tell planet to execute clip and ship
        result = activate_item(image_target,item_type,alex_geom)
        
        #download result of clip and ship
        try:
            print("attempting download:" + image_target)
            dl = download_clip_item(result,image_target,item_type,alex_geom,outdir_val)
            print("finished: " + image_target)
            print("\n")
            print("\n")
        
        #if cannot download
        except:
            print("download failed: " + image_target)
            print("\n")
            print("\n")
    
    #if cannot activate
    except:
        print("activation failed:" + image_target)
        print("not attempting download:" + image_target)
        print("\n")

print("\n")        
print('COMPLETED VALIDATION DATA')
print("\n")

