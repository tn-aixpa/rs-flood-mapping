
import configparser
import ee
import pandas as pd
from os import path, makedirs
from google.auth import compute_engine, impersonated_credentials
import json


def authenticate(project, geProject):
    service_account_secret = project.get_secret("service_account")
    service_account = service_account_secret.read_secret_value()
    private_key_secret = project.get_secret("private_key_json")
    private_key_json = private_key_secret.read_secret_value()
    
    with open(data_dir + '/key.json', "w") as outfile:
        outfile.write(private_key_json)
    
    credentials = ee.ServiceAccountCredentials(service_account, data_dir + '/key.json')
    ee.Initialize(credentials, project=geProject)
    return ee

file_basepath = "flood"
def precipitation(project,
                  geProject='',
                  before_event_start='',
                  before_event_end='',
                  after_event_start='',
                  after_event_end='',
                  aoi_coordinates_str='',
                  s1_collection='',
                  s2_collection='',
                  swater_dataset='',
                  chirps_start_date='',
                  chirps_end_date=''):
    
    global data_dir
    data_dir = f"{file_basepath}/data"
    
    try:
        shutil.rmtree(data_dir)
    except:
        print("Error deleting flood data dir")

    # Create the directory for the data
    if not path.exists(data_dir):
        makedirs(data_dir)

    ee = authenticate(project, geProject)
    
    # Parse the coordinates string into a list of lists for ee.Geometry.Polygon
    if aoi_coordinates_str:
        aoi_coordinates = [
            [float(coord.split(',')[0]), float(coord.split(',')[1])]
            for coord in aoi_coordinates_str.split(';')
        ]
    else:
        # Default AOI if not specified in config
        aoi_coordinates = [
        [10.42, 46.29],
        [11.62, 46.29],
        [11.62, 45.73],
        [10.42, 45.73]
    ]

    # Define AOI (Area of Interest)
    aoi = ee.Geometry.Polygon([aoi_coordinates])

    print("AOI successfully loaded")

    # Load CHIRPS data
    chirps = ee.ImageCollection('UCSB-CHG/CHIRPS/PENTAD') \
    .filterBounds(aoi) \
    .filterDate(chirps_start_date, chirps_end_date)  # Use config dates

    # Function to add date as a property to each image
    def add_date_property(image):
        return image.set('date', image.date().format('YYYY-MM-dd'))

    # Map the function to the collection
    chirps_with_date = chirps.map(add_date_property)
    
    # Reduce the CHIRPS data to mean precipitation values over the AOI
    def extract_precipitation(image):
        mean_precip = image.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=1000
        ).get('precipitation')  # Key for precipitation in CHIRPS
        return ee.Feature(None, {'date': image.get('date'), 'precipitation': mean_precip})

    precipitation_features = chirps_with_date.map(extract_precipitation)

    # Convert to list of dictionaries
    precipitation_list = precipitation_features.getInfo()['features']

    # Extract dates and precipitation into a DataFrame
    data = pd.DataFrame([
        {'Date': f['properties']['date'], 'Precipitation': f['properties']['precipitation']}
        for f in precipitation_list
    ])

    project.log_dataitem("precipitation", data=data, kind='table')

def save(file_name, dir, obj):
     with open(data_dir + '/' + file_name, 'wb') as file:
         pd.to_pickle(obj, file)

def read():
    with open("std1.pkl", "rb") as file:
        object = pickle.load(file)
        return object

def flood_mask(project,
               geProject='',
               before_event_start='',
               before_event_end='',
               after_event_start='',
               after_event_end='',
               aoi_coordinates_str='',
               s1_collection='',
               s2_collection='',
               swater_dataset='',
               dem_collection='',
               chirps_start_date='',
               chirps_end_date='',
               polarization='VV',
               pass_direction = 'ASCENDING',
               difference_threshold = 1.25
              ):


    global data_dir
    data_dir = f"{file_basepath}/data"
    
    try:
        shutil.rmtree(data_dir)
    except:
        print("Error deleting flood data dir")

    # Create the directory for the data
    if not path.exists(data_dir):
        makedirs(data_dir)

    ee = authenticate(project, geProject)
    
    # Parse the coordinates string into a list of lists for ee.Geometry.Polygon
    if aoi_coordinates_str:
        aoi_coordinates = [
            [float(coord.split(',')[0]), float(coord.split(',')[1])]
            for coord in aoi_coordinates_str.split(';')
        ]
    else:
        # Default AOI if not specified in config
        aoi_coordinates = [
        [10.42, 46.29],
        [11.62, 46.29],
        [11.62, 45.73],
        [10.42, 45.73]
    ]

    # Define AOI (Area of Interest)
    aoi = ee.Geometry.Polygon([aoi_coordinates])

    print("AOI successfully loaded")

    collection = ee.ImageCollection(s1_collection) \
    .filter(ee.Filter.eq('instrumentMode', 'IW')) \
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', polarization)) \
    .filter(ee.Filter.eq('orbitProperties_pass', pass_direction)) \
    .filter(ee.Filter.eq('resolution_meters', 10)) \
    .filterBounds(aoi) \
    .select(polarization)

    # SAVE AS PLATFORM ARTIFACT
    save('s1_collection', data_dir, collection)
    project.log_artifact(name='s1_collection', kind='artifact', source=data_dir + '/' + 's1_collection')

    before_collection = collection.filterDate(before_event_start, before_event_end)
    after_collection = collection.filterDate(after_event_start, after_event_end)

    # Create mosaics and apply focal mean (smoothing)
    before = before_collection.mosaic().clip(aoi).focal_mean(50, 'circle', 'meters')
    after = after_collection.mosaic().clip(aoi).focal_mean(50, 'circle', 'meters')

    # Calculate the difference and apply threshold
    difference = after.divide(before)
    flood_mask = difference.gt(difference_threshold)

    # Refine flood mask using JRC Global Surface Water
    swater = ee.Image(swater_dataset).select('seasonality')
    
    # SAVE AS PLATFORM ARTIFACT
    save('swater_dataset', data_dir, swater)
    project.log_artifact(name='swater_dataset', kind='artifact', source=data_dir + '/' + 'swater_dataset')
    
    swater_mask = swater.gte(10)
    flooded = flood_mask.where(swater_mask, 0).updateMask(flood_mask)
    #flooded = flooded.updateMask(swater_mask.Not())

    # Calculate connected components to reduce noise
    connections = flooded.connectedPixelCount(10)
    flooded = flooded.updateMask(connections.gte(10))

    # Add slope mask using DEM
    DEM = ee.Image(dem_collection)

    # SAVE AS PLATFORM ARTIFACT
    save('dem_collection', data_dir, DEM)
    project.log_artifact(name='dem_collection', kind='artifact', source=data_dir + '/' + 'dem_collection')
    
    slope = ee.Terrain.slope(DEM)
    flooded = flooded.updateMask(slope.lt(7)) #need to change slope values depend on the area

    # Add flooded areas to map
    print("Flooded areas calculated.")

    # Define Sentinel-2 functions
    def mask_clouds(image):
        qa = image.select('QA60')  # Sentinel-2 QA60 band for clouds
        cloud_mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
        return image.updateMask(cloud_mask)

    def calculate_ndwi(image):
        ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
        return ndwi.updateMask(ndwi).clip(aoi)


    # Load Sentinel-2 collection and apply cloud masking
    sentinel2 = (
        ee.ImageCollection(s2_collection)
        .filterBounds(aoi)
        .filterDate(before_event_start, after_event_end)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))  # Increased threshold from 20 to 50
        .map(mask_clouds)  # Apply cloud and shadow masking
    )
    
    # Calculate NDWI for before and after periods
    s2_before_collection = sentinel2.filterDate(before_event_start, before_event_end).map(calculate_ndwi)
    s2_after_collection = sentinel2.filterDate(after_event_start, after_event_end).map(calculate_ndwi)

    # Check if both collections have valid data
    if s2_before_collection.size().getInfo() > 0 and s2_after_collection.size().getInfo() > 0:
        # Create median composites
        s2_before = s2_before_collection.median()
        s2_after = s2_after_collection.median()
        # Calculate flood extent based on NDWI difference
        s2_flood = s2_after.subtract(s2_before).gt(0.1).rename('Flood')
        # Mask permanent water bodies
        permanent_water = ee.Image(swater_dataset).select('seasonality').gte(10)
        s2_flood = s2_flood.where(permanent_water, 0)
        # Apply mask to Sentinel-2 flood results
        s2_flood = s2_flood.updateMask(permanent_water.Not())
        file_name = 's2_flood'
        save(file_name, dir, s2_flood)
        print(f'Object successfully saved as artifact "{file_name}"')
        project.log_artifact(name="s2_flood", kind='artifact', source=data_dir + '/' + file_name)
        print("Sentinel-2 Flood Layer calculated.")
    else:
        print("No valid Sentinel-2 data available for the specified periods.")
