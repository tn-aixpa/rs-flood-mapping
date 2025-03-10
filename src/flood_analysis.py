import configparser
import ee
import pandas as pd
from os import path, makedirs
from google.auth import compute_engine, impersonated_credentials
import json
import ipywidgets as widgets
from ipyleaflet import WidgetControl

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
    
def get_s1_data(event_start, event_end, aoi, polarization='VH', pass_direction = 'ASCENDING'):
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
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))  # Increased threshold from 20 to 50
        .map(mask_clouds)  # Apply cloud and shadow masking
    )
    s2_collection = sentinel2.filterDate(event_start, event_end).map(calculate_ndwi)    
    return s2_collection

    
def compute_flooded_s1(before, after, difference_threshold=1.25, slope_threshold=7):
    # Calculate the difference and apply threshold
    difference = after.divide(before)
    flood_mask = difference.gt(difference_threshold)

    swater_mask = get_swater()
    swater_buffered = swater_mask.focal_max(100, 'square', 'meters')
    # Apply water mask correction properly
    flooded = flood_mask.updateMask(swater_buffered.Not())  # Removes flood pixels in water
    # flooded = flood_mask.where(swater_mask, 0).updateMask(flood_mask)

    # connections = flooded.connectedPixelCount(10)
    # flooded = flooded.updateMask(connections.gte(10))
    
    # slope = get_dem()
    # flooded = flooded.updateMask(slope.lt(slope_threshold))

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

def compute_area(image, label, aoi):
    band_name = image.bandNames().get(0)  # Get the first band dynamically
    pixel_area = image.multiply(ee.Image.pixelArea())  # Multiply by pixel area
    stats = pixel_area.reduceRegion(**{
        'reducer': ee.Reducer.sum(),
        'geometry': aoi,
        'scale': 30,
        'maxPixels': 1e10
    })

    # Get the area value and convert to hectares
    area_ha = stats.getNumber(band_name).divide(10000).getInfo()
    area_sqkm = round(area_ha / 100, 4) if area_ha else "No Data"  # Convert ha to sq km

    return label, round(area_ha, 2) if area_ha else "No Data", area_sqkm


def get_s2_rgb(start, end, aoi):
    return ee.ImageCollection("COPERNICUS/S2") \
    .filterBounds(aoi) \
    .filterDate(start, end) \
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) \
    .median() \
    .clip(aoi)

def flood_analysis(before_event_start, before_event_end, after_event_start, after_event_end, aoi_coords):
    aoi = read_aoi(aoi_coords)
    # aoi = ee.Geometry.Polygon([aoi_coords])
    
    before_s1 = get_s1_data(before_event_start, before_event_end, aoi)
    after_s1 = get_s1_data(after_event_start, after_event_end, aoi)
    flooded_s1 = compute_flooded_s1(before_s1, after_s1)

    before_s2 = get_s2_data(before_event_start, before_event_end, aoi)
    after_s2 = get_s2_data(after_event_start, after_event_end, aoi)
    flooded_s2 = compute_flooded_s2(before_s2, after_s2)
    
    S1_Vis = flooded_s1.visualize(**{'bands': ['VH'], 'palette': ['blue']}) 
    S2_Vis = flooded_s2.visualize(**{'bands': ['Flood'], 'palette': ['blue']}) 

    # ✅ Blend both for final merged visualization
    Merged_Flood = ee.ImageCollection([S1_Vis, S2_Vis]).mosaic()


    data = [
        before_s1, 
        after_s1, 
        get_s2_rgb(before_event_start, before_event_end, aoi), 
        get_s2_rgb(after_event_start, after_event_end, aoi),
        Merged_Flood,
        before_s2.median(),
        after_s2.median()
    ]
    return data

def get_histogram(image, region, scale=30, max_pixels=1e8, buckets=100):
    """Fetch histogram data for NDWI from a given image."""
    ndwi_histogram = image.select('NDWI').reduceRegion(
        reducer=ee.Reducer.histogram(buckets),
        geometry=region,
        scale=scale,
        maxPixels=max_pixels
    ).get('NDWI')
    return ee.Dictionary(ndwi_histogram).getInfo()
