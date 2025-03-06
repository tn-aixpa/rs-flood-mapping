import configparser
import ee
import pandas as pd
from os import path, makedirs
from google.auth import compute_engine, impersonated_credentials
import json

class Layer:
    
    def __init__(name: str, value):
        self.name = name
        self.value = value

class Analysis:

    def __init__(self,
                 name: str,
                 before_event_start: str, 
                 before_event_end: str, 
                 after_event_start: str, 
                 after_event_end: str,
                 aoi,
                 before,
                 after,
                 diff
                ):
        self.name = name
        self.before_event_start = before_event_start
        self.before_event_end = before_event_end
        self.after_event_start = after_event_start
        self.after_event_end = after_event_end
        self.aoi = aoi
        self.before = before
        self.after = after
        self.diff = diff
        
        

def init_gee(ge_project, account, private_key):
    data_dir='data'    
    with open(data_dir + '/key.json', "w") as outfile:
        outfile.write(private_key)
        
    credentials = ee.ServiceAccountCredentials(account, data_dir + '/key.json')
    ee.Initialize(credentials, project=ge_project)

def read_aoi(coord_str):
    # Parse the coordinates string into a list of lists for ee.Geometry.Polygon
    if coord_str:
        aoi_coordinates = [
            [float(coord.split(',')[0]), float(coord.split(',')[1])]
            for coord in coord_str.split(';')
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
    return aoi

def get_dem():
    DEM = ee.Image.load('WWF/HydroSHEDS/03VFDEM')
    slope = ee.Terrain.slope(DEM)
    return slope

def get_swater():
    swater = ee.Image.load('JRC/GSW1_0/GlobalSurfaceWater').select('seasonality') # try to comment it to use image from piattaform
    swater_mask = swater.gte(10)
    return swater_mask
    
def get_s1_data(event_start, event_end, aoi, polarization='VV', pass_direction = 'ASCENDING'):
    collection = ee.ImageCollection('COPERNICUS/S1_GRD') \
        .filter(ee.Filter.eq('instrumentMode', 'IW')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', polarization)) \
        .filter(ee.Filter.eq('orbitProperties_pass', pass_direction)) \
        .filter(ee.Filter.eq('resolution_meters', 10)) \
        .filterBounds(aoi) \
        .select(polarization)
    res = collection.filterDate(event_start, event_end)
    res = res.mosaic().clip(aoi).focal_mean(50, 'circle', 'meters')
    return res

def get_s2_data(event_start, event_end, aoi):
    def mask_clouds(image):
        qa = image.select('QA60')  # Sentinel-2 QA60 band for clouds
        cloud_mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
        return image.updateMask(cloud_mask)

    def calculate_ndwi(image):
        ndwi = image.normalizedDifference(['B3', 'B8']).rename('NDWI')
        return ndwi.updateMask(ndwi).clip(aoi)

    sentinel2 = (ee.ImageCollection('COPERNICUS/S2_SR')
        .filterBounds(aoi)
        .filterDate(event_start, event_end)
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 50))  # Increased threshold from 20 to 50
        .map(mask_clouds)  # Apply cloud and shadow masking
    )
    s2_collection = sentinel2.filterDate(event_start, event_end).map(calculate_ndwi)    
    return s2_collection

    
def compute_flooded_s1(before, after, difference_threshold=1.25, slope_threshold=7):
    # Calculate the difference and apply threshold
    difference = after.divide(before)
    flood_mask = difference.gt(difference_threshold)

    swater_mask = get_swater()
    flooded = flood_mask.where(swater_mask, 0).updateMask(flood_mask)

    connections = flooded.connectedPixelCount(10)
    flooded = flooded.updateMask(connections.gte(10))
    
    slope = get_dem()
    flooded = flooded.updateMask(slope.lt(slope_threshold))

    return flooded

def compute_flooded_s2(before, after):
    # Check if both collections have valid data
    if before.size().getInfo() > 0 and after.size().getInfo() > 0:
        # Create median composites
        s2_before = before.median()
        s2_after = after.median()        
        # Calculate flood extent based on NDWI difference
        s2_flood = s2_after.subtract(s2_before).gt(0.1).rename('Flood')
        # Mask permanent water bodies
        permanent_water = get_swater()
        s2_flood = s2_flood.where(permanent_water, 0)
        # Apply mask to Sentinel-2 flood results
        s2_flood = s2_flood.updateMask(permanent_water.Not())
        return s2_flood
    else:
        raise Exception("Invalid Sentinel-2 data for comparison.")


def flood_analysis(before_event_start, before_event_end, after_event_start, after_event_end, aoi_str, sensor):
    aoi = read_aoi(aoi_str)
    if sensor == 's1':
        before = get_s1_data(before_event_start, before_event_end, aoi)
        after = get_s1_data(after_event_start, after_event_end, aoi)
        flooded = compute_flooded_s1(before, after)
        return Analysis('Flood Detection Sentinel1', 
                        before_event_start, 
                        before_event_end, 
                        after_event_start, 
                        after_event_end,
                        aoi,
                        before,
                        after, 
                        flooded
                       )
    elif sensor == 's2':
        before = get_s2_data(before_event_start, before_event_end, aoi)
        after = get_s2_data(after_event_start, after_event_end, aoi)
        flooded = compute_flooded_s2(before, after)
        return Analysis('Flood Detection Sentinel2', 
                        before_event_start, 
                        before_event_end, 
                        after_event_start, 
                        after_event_end,
                        aoi,
                        before.median(),
                        after.median(), 
                        flooded
                       )
    else:
        raise Exception(f"Invalid sensor value: {sensor}. Only s1 or s2 supported")