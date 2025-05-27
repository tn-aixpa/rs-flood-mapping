import os
from glob import glob
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


CONFIG = {
    # Input folders
    "s1_zip_folder": os.path.join(BASE_DIR, "data", "sentinel_zips"),
    "s2_pre_ndwi_folder": os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(Pre-NDWI)"),
    "s2_post_ndwi_folder": os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(post-NDWI)"),

    # Shapefile
    "shapefile_path": os.path.join(BASE_DIR, "data", "AOI_Garda" ,"AOI_Rec.shp"),
    "lakes_shapefile": os.path.join(BASE_DIR, "data", "Lakes_TN", "idrspacq.shp"), #lakes data shapefile


    # Output folder (everything goes here)
    "output_folder": os.path.join(BASE_DIR, "data", "flood_outputs"),
    "temp_folder": os.path.join(BASE_DIR, "data", "flood_outputs", "temp"),  # Added temp folder
 

    # Output files
    "s1_tiff": os.path.join(BASE_DIR, "data", "flood_outputs", "S1-flood_layer.tif"),
    "s2_tiff": os.path.join(BASE_DIR, "data", "flood_outputs", "S2_flood_mask.tif"),
    "combined_tiff": os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer.tif"),
    "combined_shapefile": os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer.shp"),
    "metadata_output_path": os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer_metadata.json"),


    # Parameters
    "aoi_name": "Garda",
    #"before_flood": ["2020-09-01", "2020-09-30"],
    #"after_flood": ["2020-10-01", "2020-10-31"],
    "target_crs": "EPSG:25832",
    "flood_date": datetime.datetime.strptime("20201002", "%Y%m%d"),
    "polarization": "VV", # VV or VH
    "dem_threshold": 500, # 200-700
    "slope_threshold": 7, # 5- 15
    "noise_min_pixels": 5 # change accordingly
}

# Make sure required folders exist
os.makedirs(CONFIG["output_folder"], exist_ok=True)
os.makedirs(CONFIG["temp_folder"], exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)


# Glob sentinel-1 zip files dynamically based on config path
ZIP_FILES = glob(os.path.join(CONFIG["s1_zip_folder"], "*.zip"))