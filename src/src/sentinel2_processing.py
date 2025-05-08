
import digitalhub as dh
from digitalhub_runtime_python import handler
import glob
import rasterio
import numpy as np
import glob
import os
import geopandas as gpd
from rasterio import features
from rasterio.features import shapes
from shapely.geometry import shape
from PIL import Image
from rasterio.mask import mask
import zipfile
import contextily as ctx
from datetime import datetime
import json

def compute_mean_ndwi(files):
    ndwi_stack = []

    for file in files:
        with rasterio.open(file) as src:
            # Reproject AOI to match the raster CRS
            aoi_projected = aoi.to_crs(src.crs)

            try:
                ndwi_cropped, _ = mask(src, aoi_projected.geometry, crop=True)
                ndwi_stack.append(ndwi_cropped[0])  # First band
            except ValueError as e:
                print(f"Skipping {file}: {e}")
                continue  # Skip files that don't overlap with AOI

    ndwi_stack = np.array(ndwi_stack)
    mean_ndwi = np.mean(ndwi_stack, axis=0)

    return mean_ndwi

# Function to save both shapefile and raster of water areas
def save_water_layer(ndwi_array, transform, output_shapefile, output_raster, raster_crs, threshold=0):
    # Create binary mask of water areas
    water_mask = (ndwi_array > threshold).astype(np.uint8)

    # --- Save as TIFF ---
    height, width = water_mask.shape
    with rasterio.open(
        output_raster,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=water_mask.dtype,
        crs=raster_crs,
        transform=transform
    ) as dst:
        dst.write(water_mask, 1)
    print(f" Raster TIFF saved to {output_raster}")

    # --- Convert mask to polygons and save as shapefile ---
    results = shapes(water_mask, mask=water_mask, transform=transform)
    geometries = [shape(geom) for geom, _ in results]
    gdf = gpd.GeoDataFrame({'geometry': geometries}, crs=raster_crs)
    gdf.to_file(output_shapefile)
    print(f" Shapefile saved to {output_shapefile} with CRS: {raster_crs}")


file_basepath = "/app/files"
@handler()
def precipitation(project, af1, af2, shp, before_event_start='', before_event_end='', after_event_start='', after_event_end='', aoi_label='', shape_label=''):
    global aoi
    data_dir = f"{file_basepath}/data"   
    try:
        shutil.rmtree(data_dir)
    except:
        print("Error deleting flood data dir")

    # Create the directory for the data
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)

    pre_flood_folder = af1.download(data_dir)
    post_flood_folder = af2.download(data_dir)
    aoi_path = shp.download(data_dir)

        
    # Define pre-flood and post-flood folders
    pre_flood_folder = pre_flood_folder + "/preprocess/NDWI"
    post_flood_folder = post_flood_folder + "/preprocess/NDWI"
    aoi_path = aoi_path + "/" + shape_label + ".shp" #crop the Tile with AOI
    output_folder = data_dir + f"{aoi_label}/Outputs"

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    # Output shapefile path
    flood_shapefile = os.path.join(output_folder, f"{aoi_label}_flood_layer.shp")
    metadata_output_path = os.path.join(output_folder, f"{aoi_label}_metadata.json")

    # Find all NDWI TIFF files in each folder
    pre_flood_files = sorted(glob.glob(os.path.join(pre_flood_folder, "*.tif")))
    post_flood_files = sorted(glob.glob(os.path.join(post_flood_folder, "*.tif")))
    
    # Print the count only
    print(f" Found {len(pre_flood_files)} pre-flood images.")
    print(f" Found {len(post_flood_files)} post-flood images.")

    # Function to compute the mean NDWI across multiple images
    # Load AOI
    aoi = gpd.read_file(aoi_path)
    
    # Compute mean NDWI for pre-flood and post-flood images
    ndwi_pre = compute_mean_ndwi(pre_flood_files)
    ndwi_post = compute_mean_ndwi(post_flood_files)

    #CRS
    with rasterio.open(post_flood_files[0]) as src:
        transform = src.transform
        raster_crs = src.crs

    # Define output paths
    output_shapefile = os.path.join(output_folder, f"{aoi_label}_flood_layer.shp")
    output_raster = os.path.join(output_folder, f"{aoi_label}_flood_layer.tif")

    # Run function
    save_water_layer(ndwi_post, transform, output_shapefile, output_raster, raster_crs, threshold=0)

    # === Build flood period ===
    flood_period = {
        "before": f"{before_event_start} to {before_event_end}",
        "after": f"{after_event_start} to {after_event_end}"
    }
    
    # === Count NDWI images ===
    pre_images = glob.glob(os.path.join(pre_flood_folder, "*.tif"))
    post_images = glob.glob(os.path.join(post_flood_folder, "*.tif"))

    # === Attempt to load flood shapefile and compute flooded area ===
    if os.path.exists(flood_shapefile):
        flood_gdf = gpd.read_file(flood_shapefile)
        if flood_gdf.crs and flood_gdf.crs.is_geographic:
            flood_gdf = flood_gdf.to_crs(epsg=3857)
        total_flooded_area_sqkm = round(flood_gdf.geometry.area.sum() / 1e6, 2)
    else:
        print(f" Flood shapefile not found: {flood_shapefile}")
        total_flooded_area_sqkm = None

    # === Compile metadata dictionary ===
    metadata = {
        "flood_layer_calculated": "Sentinel-2",
        "pre_images_count": len(pre_images),
        "post_images_count": len(post_images),
        "aoi_name": aoi_label,
        "flood_period": flood_period,
        "image_date_range": [before_event_start, after_event_end],
        "processed_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "outputpath_shapefile_name": flood_shapefile,
        "notes": "Auto-generated metadata during flood layer processing",
        "total_flooded_area_sqkm": total_flooded_area_sqkm
    }

    # === Save metadata to JSON in correct location ===
    with open(metadata_output_path, "w") as f:
        json.dump(metadata, f, indent=4)

    # Done
    print(f" Metadata saved at: {metadata_output_path}")
    print(json.dumps(metadata, indent=4))

    project.log_artifact(name=aoi_label, kind='artifact', source=output_folder)
