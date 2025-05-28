import os
import sys
import json
import glob
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
import xml.etree.ElementTree as ET
from snapista import Graph, Operator
import zipfile
from io import BytesIO
from scipy.ndimage import label
import numpy as np
from scipy.ndimage import gaussian_gradient_magnitude
from utils.skd_handler import upload_artifact
from shapely.wkt import loads, dumps
from rasterio.merge import merge

import digitalhub as dh


def load_aoi():
    print(f"Loading AOI from {shapefile_path}")
    gdf = gpd.read_file(shapefile_path)
    if not gdf.crs:
        gdf.set_crs(target_crs, inplace=True)
    elif gdf.crs.to_string() != target_crs:
        gdf = gdf.to_crs(target_crs)
    return gdf

# def load_lakes():
#     print(f"Loading lakes shapefile from {lakes_shapefile}")
#     lakes_path = lakes_shapefile
#     if not lakes_path or not os.path.exists(lakes_path):
#         print("Lakes shapefile not found or not configured.")
#         return None
#     lakes = gpd.read_file(lakes_path)
#     lakes = lakes.to_crs(target_crs)
#     return lakes

def load_lakes():
    print(f"Loading lakes shapefile from {lakes_shapefile}")
    lakes_path = lakes_shapefile
    if not lakes_path or not os.path.exists(lakes_path):
        print("Lakes shapefile not found or not configured.")
        return None
    lakes = gpd.read_file(lakes_path)
    lakes = lakes.to_crs(target_crs)
    return lakes

def load_rivers():
    print(f"Loading rivers shapefile from {rivers_shapefile}")
    rivers_path = rivers_shapefile
    if not rivers_path or not os.path.exists(rivers_path):
        print("Rivers shapefile not found or not configured.")
        return None
    rivers = gpd.read_file(rivers_path)
    rivers = rivers.to_crs(target_crs)
    rivers_buffered = rivers.buffer(river_buffer_meters)
    return gpd.GeoDataFrame(geometry=rivers_buffered, crs=target_crs)


def compute_mean_ndwi(files, aoi_gdf):
    stack = []
    nodata_val = -9999.0
    ref_crs = target_crs
    resolution = 10
    bounds = aoi_gdf.total_bounds
    width = int((bounds[2] - bounds[0]) / resolution)
    height = int((bounds[3] - bounds[1]) / resolution)
    transform = rasterio.transform.from_bounds(*bounds, width, height)

    for f in files:
        with rasterio.open(f) as src:
            try:
                aoi_proj = aoi_gdf.to_crs(src.crs)
                ndwi_crop, src_transform = mask(src, aoi_proj.geometry, crop=True, nodata=nodata_val)
                ndwi_crop = ndwi_crop[0]

                output = np.full((height, width), nodata_val, dtype=np.float32)
                reproject(
                    source=ndwi_crop,
                    destination=output,
                    src_transform=src_transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=ref_crs,
                    resampling=Resampling.bilinear,
                    src_nodata=nodata_val,
                    dst_nodata=nodata_val
                )
                stack.append(output)
            except ValueError:
                print(f"Skipping {f}: no AOI overlap")

    if not stack:
        raise ValueError("No valid NDWI files found.")
    return np.nanmean(np.stack(stack), axis=0), transform, ref_crs, height, width

def save_s2_flood_layer(ndwi, transform, crs, height, width, threshold, raster_out):
    mask_out = (ndwi > threshold).astype(np.uint8)
    with rasterio.open(raster_out, "w", driver="GTiff", height=height, width=width,
                       count=1, dtype="uint8", crs=crs, transform=transform, nodata=0) as dst:
        dst.write(mask_out, 1)
    print(f"Saved S2 flood mask: {raster_out}")

def combine_s1_s2(s1_path, s2_path, combined_tiff, combined_shp):
    print("Combining Sentinel-1 and Sentinel-2 masks...")
    try:
        with rasterio.open(s1_path) as s1, rasterio.open(s2_path) as s2:
            s1_data = s1.read(1)
            s2_data = s2.read(1)

            s1_valid = s1_data != (s1.nodata or 0)
            s1_flood = s1_data > 0

            s2_aligned = np.zeros(s1_data.shape, dtype=np.uint8)
            reproject(
                source=s2_data,
                destination=s2_aligned,
                src_transform=s2.transform,
                src_crs=s2.crs,
                dst_transform=s1.transform,
                dst_crs=s1.crs,
                resampling=Resampling.nearest,
                src_nodata=s2.nodata or 0,
                dst_nodata=0
            )

            s2_valid = s2_aligned != 0
            s2_flood = s2_aligned == 1

            combined = np.zeros_like(s1_data, dtype=np.uint8)
            combined[s1_valid & s1_flood] = 255
            combined[s2_valid & s2_flood] = 255

            transform, width, height = calculate_default_transform(
                s1.crs, target_crs, s1.width, s1.height, *s1.bounds
            )
            combined_reprojected = np.zeros((height, width), dtype=np.uint8)

            reproject(
                source=combined,
                destination=combined_reprojected,
                src_transform=s1.transform,
                src_crs=s1.crs,
                dst_transform=transform,
                dst_crs=target_crs,
                resampling=Resampling.nearest
            )

            aoi = load_aoi()
            lakes = load_lakes()
            rivers = load_rivers()
            if lakes is not None:
                aoi = gpd.overlay(aoi, lakes, how='difference')
            if rivers is not None:
                aoi = gpd.overlay(aoi, rivers, how='difference')

            with rasterio.open("/tmp/combined_unclipped.tif", "w", driver="GTiff",
                               height=height, width=width, count=1, dtype="uint8",
                               crs=target_crs, transform=transform, nodata=0) as tmp:
                tmp.write(combined_reprojected, 1)

            with rasterio.open("/tmp/combined_unclipped.tif") as tmp_src:
                clipped, out_transform = mask(tmp_src, aoi.geometry, crop=True, nodata=0)
                final_meta = tmp_src.meta.copy()
                final_meta.update({
                    "height": clipped.shape[1],
                    "width": clipped.shape[2],
                    "transform": out_transform
                })

            labeled, num_features = label(clipped[0] == 255)
            sizes = np.bincount(labeled.ravel())
            small_mask = np.isin(labeled, np.where(sizes < noise_min_pixels)[0])
            cleaned = clipped[0].copy()
            cleaned[small_mask] = 0

            with rasterio.open(combined_tiff, "w", **final_meta) as dst:
                dst.write(cleaned, 1)

            results = shapes(cleaned, mask=cleaned == 255, transform=out_transform)
            geoms = [shape(g) for g, _ in results]
            if geoms:
                gdf = gpd.GeoDataFrame({"geometry": geoms}, crs=target_crs)
                gdf.to_file(combined_shp)

            print(f"Final cleaned TIFF saved: {combined_tiff}")
            print(f"Final shapefile saved: {combined_shp}")

    except Exception as e:
        print(f"Fusion failed: {e}")
        raise


def write_metadata():
    try:
        metadata = {
            "aoi_name": aoi_name,
            "flood_date": flood_date.strftime("%Y-%m-%d %H:%M:%S"),
            "sentinel1_used": Path(s1_tiff).exists(),
            "sentinel2_used": Path(s2_tiff).exists(),
            "s1_image_count": len(glob(os.path.join(s1_zip_folder, "*.zip"))),
            "s2_pre_ndwi_count": len(glob(os.path.join(s2_pre_ndwi_folder, "preprocess", "NDWI", "*.tif"))),
            "s2_post_ndwi_count": len(glob(os.path.join(s2_post_ndwi_folder,"preprocess", "NDWI", "*.tif"))),
            "processed_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "output_tiff": combined_tiff,
            "output_shapefile": combined_shapefile
        }

        # Compute total flood area in sq. km if shapefile exists
        shp = combined_shapefile
        if Path(shp).exists():
            gdf = gpd.read_file(shp)
            if gdf.crs.is_geographic:
                gdf = gdf.to_crs(target_crs)
            metadata["total_flooded_area_sqkm"] = round(gdf.geometry.area.sum() / 1e6, 2)
        else:
            metadata["total_flooded_area_sqkm"] = "Not computed"

        with open(metadata_output_path, "w") as f:
            json.dump(metadata, f, indent=4)

        print("Metadata saved with image counts and flood area.")
    except Exception as e:
        print(f"Failed to write metadata: {e}")


#args=['/shared/launch.sh', 'sentinel2_post_flood','sentinel2_pre_flood','sentinel1_post_flood','shapesAOI', 'AOI_Rec.shp', 'shapelake's, 'nameofShapelake' , 'output_flood_mask', '20201002']

#{"input1": "sentinel2_post_flood","input2": "sentinel2_pre_flood","input3": "sentinel1_post_flood","input4": "AOI_Garda","input5":"AOI_Rec.shp","input6": "Lakes_TN", "input7": "idrspacq.shp","input8": "Rivers_TN", "input9": "cif_pta2022_v", "input10": "output_flood_mask","input11": "20201002"}   


def extract_date_from_filename(filename):
    try:
        print(f"Extracting date from filename: {filename}")
        parts = filename.split('_')
        date_str = parts[4][:8]
        print (f"Extracted date string: {date_str} from filename: {filename}")
        return datetime.strptime(date_str, "%Y%m%d")
    except Exception as e:
        print(f"Failed to extract date from {filename}: {str(e)}")
        return None

def get_aoi_wkt_and_projection():
    try:
        gdf = gpd.read_file(shapefile_path)
        gdf = gdf.to_crs(epsg=4326)
        aoi_geom = gdf.geometry.union_all()
        print("AOI converted to WKT with CRS EPSG:4326")
        return aoi_geom.wkt, gdf.crs
    except Exception as e:
        print(f"Failed to process shapefile {shapefile_path}: {str(e)}")
        raise

def check_aoi_overlap(zip_path, aoi_wkt):
    print(f"DEBUG: Using manifest.safe for {zip_path}")
    try:
        if not isinstance(aoi_wkt, str):
            print(f"Invalid aoi_wkt type: {type(aoi_wkt)}")
            return False
        with zipfile.ZipFile(zip_path, 'r') as z:
            manifest_path = [f for f in z.namelist() if f.endswith('manifest.safe')][0]
            print(f"Found manifest: {manifest_path}")
            with z.open(manifest_path) as f:
                manifest_content = f.read()
        root = ET.parse(BytesIO(manifest_content)).getroot()
        footprint = None
        for coordinates in root.findall(".//gml:coordinates", namespaces={'gml': 'http://www.opengis.net/gml'}):
            coords = coordinates.text.strip().split()
            print(f"Coordinates: {coords[:5]}...")
            coords = [tuple(map(float, c.split(','))) for c in coords]
            footprint = shape({
                'type': 'Polygon',
                'coordinates': [[(lon, lat) for lat, lon in coords]]
            })
            break
        if not footprint:
            print(f"No footprint found in manifest for {zip_path}")
            return False
        gdf_footprint = gpd.GeoDataFrame(geometry=[footprint], crs="EPSG:4326")
        aoi = loads(aoi_wkt)
        intersects = gdf_footprint.geometry.iloc[0].intersects(aoi)
        print(f"AOI overlap check for {zip_path}: {'Success' if intersects else 'No overlap'}")
        return intersects
    except Exception as e:
        print(f"Failed to check AOI overlap for {zip_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

PROJ4_TEXT = 'PROJCS["ETRS89 / UTM zone 32N", GEOGCS["ETRS89", DATUM["European Terrestrial Reference System 1989", SPHEROID["GRS 1980",6378137.0, 298.257222101, AUTHORITY["EPSG","7019"]], TOWGS84[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], AUTHORITY["EPSG","6258"]], PRIMEM["Greenwich", 0.0, AUTHORITY["EPSG","8901"]], UNIT["degree", 0.017453292519943295], AXIS["Geodetic longitude", EAST], AXIS["Geodetic latitude", NORTH], AUTHORITY["EPSG","4258"]], PROJECTION["Transverse_Mercator", AUTHORITY["EPSG","9807"]], PARAMETER["central_meridian", 9.0], PARAMETER["latitude_of_origin", 0.0], PARAMETER["scale_factor", 0.9996], PARAMETER["false_easting", 500000.0], PARAMETER["false_northing", 0.0], UNIT["m", 1.0], AXIS["Easting", EAST], AXIS["Northing", NORTH], AUTHORITY["EPSG","25832"]]'


def preprocess_and_subset(zip_path, geo_wkt):
    out_file = os.path.join(temp_folder, os.path.basename(zip_path).replace(".zip", "_preprocessed.tif"))
    try:
        if not os.path.exists(zip_path):
            print(f"ZIP file not found: {zip_path}")
            return None
        if not check_aoi_overlap(zip_path, geo_wkt):
            print(f"Skipping {zip_path}: No AOI overlap")
            return None
        g = Graph()
        g.add_node(Operator("Read", file=zip_path, formatName="SENTINEL-1"), node_id="read")
        g.add_node(Operator("Apply-Orbit-File", orbitType="Sentinel Precise (Auto Download)", continueOnFail="true"), node_id="orbit", source="read")
        g.add_node(Operator("Calibration", outputSigmaBand="true", outputImageScaleInDb="false", selectedPolarisations=polarization), node_id="calibration", source="orbit")
        g.add_node(Operator("Speckle-Filter", filter="Lee", filterSizeX="5", filterSizeY="5"), node_id="speckle", source="calibration")
        g.add_node(Operator("Subset", geoRegion=geo_wkt), node_id="subset", source="speckle")
        g.add_node(Operator("Terrain-Correction", demName="SRTM 3Sec", pixelSpacingInMeter="10.0", mapProjection=PROJ4_TEXT), node_id="tc", source="subset")
        g.add_node(Operator("Write", file=out_file, formatName="GeoTIFF-BigTIFF"), node_id="write", source="tc")
        g.run()
        if not os.path.exists(out_file):
            print(f"Output file not created: {out_file}")
            return None
        print(f"Preprocessed file saved to {out_file}")
        return out_file
    except Exception as e:
        print(f"Error preprocessing {zip_path}: {str(e)}")
        return None

def detect_flood(input_raster, output_path):
    try:
        with rasterio.open(input_raster) as src:
            band = src.read(1)
            elevation = src.read(2) if src.count > 1 else None
            profile = src.profile

            flood_mask = (band < 1.13E-2).astype(np.uint8)
            if elevation is not None:
                flood_mask[elevation > dem_threshold] = 0
                slope = np.degrees(np.arctan(gaussian_gradient_magnitude(elevation, sigma=1)))
                flood_mask[slope > slope_threshold] = 0

            structure = np.ones((3, 3), dtype=int)
            labeled, num_features = label(flood_mask, structure=structure)
            counts = np.bincount(labeled.ravel())
            remove_labels = np.where(counts < noise_min_pixels)[0]
            mask = np.isin(labeled, remove_labels)
            flood_mask[mask] = 0

        profile.update(dtype=rasterio.uint8, count=1)
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(flood_mask, 1)
        print(f"Flood detection result saved to {output_path}")
    except Exception as e:
        print(f"Error in flood detection for {input_raster}: {str(e)}")
        raise

from glob import glob
def batch_process():

    S1_ZIP_PATH = s1_zip_folder
    ZIP_FILES = glob(os.path.join(S1_ZIP_PATH, "*.zip"))
    TEMP_FOLDER = temp_folder
    CROPPED_TIF_PATH = s1_tiff
    FLOOD_DATE = flood_date
    
    try:
        geo_wkt, target_crs = get_aoi_wkt_and_projection()
        processed_rasters = []
        if not ZIP_FILES:
            print(f"No ZIP files found in {S1_ZIP_PATH}")
            print(f"[ERROR] No ZIP files found in {S1_ZIP_PATH}")
            return
        for file in sorted(ZIP_FILES):
            print(f"Processing file: {file}")
            file_name = os.path.basename(file)
            file_date = extract_date_from_filename(file_name)
            if file_date and file_date >= FLOOD_DATE:
                print(f"Processing {file_name}")
                print(f"[INFO] Preprocessing and subsetting {file_name}")
                result = preprocess_and_subset(file, geo_wkt)
                if result:
                    processed_rasters.append(result)
            else:
                print(f"Skipping {file_name}: Date {file_date} not after {FLOOD_DATE}")
                print(f"[INFO] Skipping {file_name}: Date {file_date} not after {FLOOD_DATE}")
        if not processed_rasters:
            print("No usable preprocessed rasters found")
            print("[ERROR] No usable preprocessed rasters found.")
            return
        src_files = [rasterio.open(fp) for fp in processed_rasters]
        mosaic, out_trans = merge(src_files, method="max")
        meta = src_files[0].meta.copy()
        meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_trans,
            "compress": "lzw",
            "BIGTIFF": "YES"
        })
        merged_path = os.path.join(TEMP_FOLDER, "merged_cropped.tif")
        with rasterio.open(merged_path, "w", **meta) as dest:
            dest.write(mosaic)
        for src in src_files:
            src.close()
        print(f"Merged cropped raster saved to {merged_path}")
        print(f"[INFO] Merged cropped raster saved to {merged_path}")
        detect_flood(merged_path, CROPPED_TIF_PATH)
        for temp in processed_rasters:
            if os.path.exists(temp):
                os.remove(temp)
        if os.path.exists(merged_path):
            os.remove(merged_path)
        print("Cleanup complete. Final flood map ready")
        print("[INFO] Cleanup complete. Final flood map ready.")
    except Exception as e:
        print(f"Batch processing failed: {str(e)}")
        print(f"[ERROR] Batch processing failed: {str(e)}")



# Example command to run the script:
# python main.py '{"input1": "sentinel1_GRD_postflood","input2": "sentinel2_post_flood","input3": "sentinel2_pre_flood","input4": "AOI_TN","input5":"AOI_Rec.shp","input6": "Lakes_TN", "input7": "idrspacq.shp","input8": "Rivers_TN", "input9": "cif_pta2022_v.shp", "input10": "output_flood_mask","input11": "20201002", "input12": "EPSG:25832", "input13": "VV", "input14": 200, "input15": 5, "input16": 5, "input17": 2}'


if __name__ == "__main__":

    global target_crs, flood_date, polarization, dem_threshold, slope_threshold, noise_min_pixels, shapefile_path, lakes_shapefile, combined_shapefile, combined_tiff, s1_tiff, s2_tiff, metadata_output_path, output_folder, temp_folder,before_flood,artifact_name,after_flood
    
    args = sys.argv[1].replace("'","\"")
    json_input = json.loads(args)
    project_name=os.environ["PROJECT_NAME"]
    input1 = json_input['input1'] # Sentine2 pre-flood
    input2 = json_input['input2'] # Sentinel2 post-flood
    input3 = json_input['input3'] # Sentinel1 post-flood
    input4 = json_input['input4'] # AOI Shape aritfact
    input5 = json_input['input5'] # AOI Shpe file name
    input6 = json_input['input6'] # Lake Shape artifact
    input7 = json_input['input7'] # Lake Shape file name
    input8 = json_input['input8'] # Rivers Shape artifact
    input9 = json_input['input9'] # Rivers Shape file name
    input10 = json_input['input10'] # Output artifact name
    input11 = json_input['input11'] # flood date
    input12 = json_input['input12'] # target_crs
    input13 = json_input['input13'] # polarization (VV or VH)
    input14 = json_input['input14'] # dem_threshold (200-700)
    input15 = json_input['input15'] # slope_threshold (5- 15)
    input16 = json_input['input16'] # noise_min_pixels 5
    input17 = json_input['input17'] # river_buffer_meters 2
    
    BASE_DIR = '.'
    # Input folders
    s1_zip_folder = os.path.join(BASE_DIR, "data", "sentinel_zips")
    s2_pre_ndwi_folder = os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(Pre-NDWI)")
    s2_post_ndwi_folder = os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(post-NDWI)")
    shapefile_path = os.path.join(BASE_DIR, "data", input4 , input5) # "AOI_Garda" ,"AOI_Rec.shp"
    lakes_shapefile = os.path.join(BASE_DIR, "data", input6, input7) # "Lakes_TN", "idrspacq.shp"
    rivers_shapefile = os.path.join(BASE_DIR, "data", input8, input9) # "Rivers_TN", "cif_pta2022_v.shp"

    # Output folder (everything goes here)
    output_folder = os.path.join(BASE_DIR, "data", "flood_outputs")
    temp_folder = os.path.join(BASE_DIR, "data", "flood_outputs", "temp")  # Added temp folder
 

    # Output files
    s1_tiff = os.path.join(BASE_DIR, "data", "flood_outputs", "S1-flood_layer.tif")
    s2_tiff = os.path.join(BASE_DIR, "data", "flood_outputs", "S2_flood_mask.tif")
    combined_tiff = os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer.tif")
    combined_shapefile = os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer.shp")
    metadata_output_path = os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer_metadata.json")

    # Make sure required folders exist
    os.makedirs(s1_zip_folder, exist_ok=True)
    os.makedirs(s2_post_ndwi_folder, exist_ok=True)
    os.makedirs(s2_pre_ndwi_folder, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", input4), exist_ok=True)  # Ensure AOI folder exists
    os.makedirs(os.path.join(BASE_DIR, "data", input6), exist_ok=True)  # Ensure Lakes folder exists
    os.makedirs(os.path.join(BASE_DIR, "data", input8), exist_ok=True)  # Ensure Rivers folder exists
    # Ensure output folders exist
    os.makedirs(output_folder, exist_ok=True)
    # Ensure temp folder exists
    os.makedirs(temp_folder, exist_ok=True)

    # Download (Shapefile, Zips)
    project = dh.get_or_create_project(project_name)
    # Download artifacts
    print(f"Downloading AOI shape artifact for project: {project_name} Name: {input4}")
    shp_artifact = project.get_artifact(input4)
    shp_path =  shp_artifact.download(os.path.join(BASE_DIR, "data", input4), overwrite=True)
    print(f"Downloading lake shape artifact for project: {project_name} Name: {input6}")
    lake_artifact = project.get_artifact(input6)
    lake_shp_path = lake_artifact.download(os.path.join(BASE_DIR, "data", input6), overwrite=True)
    print(f"Downloading River artifacts for project: {project_name} Name: {input8}")
    rivers_artifact = project.get_artifact(input8)
    rivers_shp_path = rivers_artifact.download(os.path.join(BASE_DIR, "data", input8), overwrite=True)
    print(f"Downloading Sentinel-1 artifact for project: {project_name} Name: {input1}")
    sentinel1_artifact = project.get_artifact(input1)
    sentinel1_zip_path = sentinel1_artifact.download(s1_zip_folder, overwrite=True)
    print(f"Downloading Sentinel-2 post-flood artifact for project: {project_name} Name: {input2}")
    sentinel2_postflood_artifact = project.get_artifact(input2)
    sentinel2_zip_path2 = sentinel2_postflood_artifact.download(s2_post_ndwi_folder, overwrite=True)
    print(f"Downloading Sentinel-2 pre-flood artifact for project: {project_name} Name: {input3}")
    sentinel2_preflood_artifact = project.get_artifact(input3)
    sentinel2_zip_path1 = sentinel2_preflood_artifact.download(s2_pre_ndwi_folder, overwrite=True)
    artifact_name = input10

    print(f"flood date: {input11}")

    # Set up configuration
    aoi_name = input5
    flood_date = datetime.strptime(input11, "%Y%m%d") # "20201002"
    target_crs = input12; # "EPSG:25832" #input12
    polarization = input13, # VV or VH #input13
    dem_threshold = input14, # 200-700 #input14
    slope_threshold = input15, # 5- 15 #input15
    noise_min_pixels= input16 # input16
    river_buffer_meters= input17 # input17

    
    # Run the pipeline
    print("Starting Flood Mapping Pipeline")
    aoi = load_aoi()

    ndwi_post, transform, crs, height, width = compute_mean_ndwi(
        glob(os.path.join(s2_post_ndwi_folder, "preprocess", "NDWI","*.tif")), aoi
    )
    
    save_s2_flood_layer(
        ndwi_post, transform, crs, height, width, threshold=0.0,
        raster_out=s2_tiff
    )

    batch_process()

    combine_s1_s2(s1_tiff, s2_tiff,combined_tiff,combined_shapefile)

    write_metadata()

    print("Pipeline complete.")

    print(f"Upoading artifact: {artifact_name}, {artifact_name}")
    upload_artifact(artifact_name=artifact_name,project_name=project_name,src_path=output_folder)

