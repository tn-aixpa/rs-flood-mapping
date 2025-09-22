import os
import sys
import json
import glob
import json
from datetime import datetime, timedelta #updated line
from pathlib import Path
import numpy as np
from rasterio.crs import CRS
from scipy.ndimage import binary_opening, binary_closing
import rasterio
from rasterio.mask import mask
from skimage.morphology import remove_small_objects
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
from shapely import wkt
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
import shutil
import pyproj
from shapely.ops import transform
from shapely.geometry import mapping
from osgeo import gdal
import geopandas as gpd
from shapely import wkt
from osgeo import gdal 
gdal.UseExceptions()


import digitalhub as dh

def load_aoi():
    # geom_wkt = geometry.wkt # or directly use your global 'geometry'
    geom = wkt.loads(geo_wkt)
    gdf = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:4326")
    return gdf.to_crs(target_crs)

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

######### updated s2 processing ####################
def run_s2():

    geometry = wkt.loads(geo_wkt)

    def reproject_geometry(geom, src_crs, dst_crs):
        if src_crs != dst_crs:
            project = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True).transform
            return transform(project, geom)
        return geom

    def compute_mean_ndwi(files, geometry, fill_value=0.0,
                          reference_shape=None, reference_transform=None, reference_crs=None):  # UPDATED
        ndwi_stack = []
        ref_shape = reference_shape
        ref_transform = reference_transform
        ref_crs = reference_crs

        for file in files:
            with rasterio.open(file) as src:
                try:
                    geom_proj = reproject_geometry(geometry, "EPSG:4326", src.crs)
                    geom_geojson = [mapping(geom_proj)]
                    ndwi_cropped, transform = mask(src, geom_geojson, crop=True, filled=True, nodata=fill_value)
                    ndwi = ndwi_cropped[0]

                    if ref_shape is None:
                        ref_shape = ndwi.shape
                        ref_transform = transform
                        ref_crs = src.crs
                    elif ndwi.shape != ref_shape:  # NEW BLOCK
                        ndwi_resampled = np.full(ref_shape, fill_value, dtype=np.float32)
                        rasterio.warp.reproject(
                            source=ndwi,
                            destination=ndwi_resampled,
                            src_transform=transform,
                            src_crs=src.crs,
                            dst_transform=ref_transform,
                            dst_crs=ref_crs,
                            resampling=Resampling.bilinear,
                            src_nodata=fill_value,
                            dst_nodata=fill_value
                        )
                        ndwi = ndwi_resampled

                    ndwi_stack.append(ndwi)

                except ValueError as e:
                    print(f"Skipping {file}: {e}")
                    continue

        if not ndwi_stack:
            print("No valid NDWI rasters found for AOI. Skipping Sentinel-2 processing.")
            return None, None, None  # UPDATED

        mean_ndwi = np.mean(np.array(ndwi_stack), axis=0)
        return mean_ndwi, ref_transform, ref_crs

    # --- PROCESS NDWI ---
    ndwi_pre, pre_transform, pre_crs = compute_mean_ndwi(s2_pre_flood_files, geometry)
    if ndwi_pre is None:  # NEW CHECK
        return

    ndwi_post, _, _ = compute_mean_ndwi(
        s2_post_flood_files,
        geometry,
        reference_shape=ndwi_pre.shape,
        reference_transform=pre_transform,
        reference_crs=pre_crs
    )
    if ndwi_post is None:  # NEW CHECK
        return

    ndwi_diff = ndwi_post - ndwi_pre

    # --- FLOOD DETECTION ---
    ndwi_threshold = 0.2
    change_threshold = 0.1

    pre_water = ndwi_pre > ndwi_threshold
    post_water = ndwi_post > ndwi_threshold
    new_water = (post_water.astype(int) - pre_water.astype(int)) == 1
    flood_pixels = (ndwi_diff > change_threshold) & new_water

    def save_flood_mask_tiff(flood_array, transform, crs, output_path, nodata=0):
        height, width = flood_array.shape
        flood_array = flood_array.astype(rasterio.uint8)
        with rasterio.open(
            output_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype=rasterio.uint8,
            crs=crs,
            transform=transform,
            nodata=nodata
        ) as dst:
            dst.write(flood_array, 1)
        print(f"Flood mask saved to: {output_path}")

    output_tiff_path = os.path.join(output_folder, "S2-flood_layer.tif")
    save_flood_mask_tiff(flood_pixels, pre_transform, pre_crs, output_tiff_path)


########################FILE 2#########################################
# S1 - Processing

def extract_date_from_filename(filename):
    try:
        parts = filename.split('_')
        return datetime.strptime(parts[4][:8], "%Y%m%d")
    except:
        return None

def get_aoi_wkt():
    if not geo_wkt:
        raise ValueError("['geometry'] must be defined.")
    return geo_wkt

def check_aoi_overlap(zip_path, aoi_wkt):
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            manifest = [f for f in z.namelist() if f.endswith('manifest.safe')][0]
            with z.open(manifest) as f:
                content = f.read()
        root = ET.parse(BytesIO(content)).getroot()
        coords = root.find(".//gml:coordinates", namespaces={'gml': 'http://www.opengis.net/gml'})
        if coords is None:
            return False
        coords = [tuple(map(float, c.split(','))) for c in coords.text.strip().split()]
        poly = shape({'type': 'Polygon', 'coordinates': [[(lon, lat) for lat, lon in coords]]})
        aoi = wkt.loads(aoi_wkt)
        return poly.intersects(aoi)
    except:
        return False

def preprocess(zip_path, geo_wkt):
    out_file = os.path.join(temp_folder, os.path.basename(zip_path).replace(".zip", "_preprocessed.tif"))
    try:
        if not check_aoi_overlap(zip_path, geo_wkt):
            return None
        g = Graph()
        g.add_node(Operator("Read", file=zip_path, formatName="SENTINEL-1"), node_id="read")
        g.add_node(Operator("Apply-Orbit-File", orbitType="Sentinel Precise (Auto Download)", continueOnFail="true"), node_id="orbit", source="read")
        g.add_node(Operator("Calibration", outputSigmaBand="true", outputImageScaleInDb="false", selectedPolarisations=polarization), node_id="calibration", source="orbit")
        g.add_node(Operator("Speckle-Filter", filter="Lee", filterSizeX="5", filterSizeY="5"), node_id="speckle", source="calibration")
        g.add_node(Operator("Subset", geoRegion=geo_wkt), node_id="subset", source="speckle")
        g.add_node(Operator("Terrain-Correction", demName="SRTM 3Sec", pixelSpacingInMeter="10.0", mapProjection=proj4_text, outputDEM=True), node_id="tc", source="subset")
        g.add_node(Operator("Write", file=out_file, formatName="GeoTIFF-BigTIFF"), node_id="write", source="tc")
        g.run()
        return out_file if os.path.exists(out_file) else None
    except:
        return None
    
####### updated version 4  ####################
def detect_change(pre_path, post_path, output_path):
    with rasterio.open(pre_path) as pre, rasterio.open(post_path) as post:
        profile = post.profile
        pre_band = pre.read(1).astype(np.float32)
        post_band = post.read(1).astype(np.float32)

        # Avoid division by zero
        pre_band[pre_band <= 0] = 1e-6
        post_band[post_band <= 0] = 1e-6

        # Change detection using log-ratio
        log_ratio = 10 * np.log10(post_band / pre_band)
        flood_mask = (log_ratio < -5)
        flood_mask = remove_small_objects(flood_mask, min_size=200)

        flood_mask = flood_mask.astype(np.uint8)

        # --- slopemap in datalake: slope masking ---
        try:
            # Step 1: Clip slope map to AOI
            aoi_geom = wkt.loads(geo_wkt)  # geometry is already defined globally
            print(f"[INFO] AOI geometry: {aoi_geom}")
            aoi_gdf = gpd.GeoDataFrame(geometry=[aoi_geom], crs="EPSG:4326")

            # Read slope CRS
            with rasterio.open(slope_map_path) as slope_src:
                slope_crs = slope_src.crs

            # Reproject AOI to slope CRS
            if aoi_gdf.crs != slope_crs:
                aoi_gdf = aoi_gdf.to_crs(slope_crs)

            bounds = aoi_gdf.total_bounds  # xmin, ymin, xmax, ymax

            # Prepare GDAL Translate window
            window = [bounds[0], bounds[3], bounds[2], bounds[1]]  # xmin, ymax, xmax, ymin

            print(f"[INFO] Clipping slope map to AOI bounds: {window}")

            clipped_slope_path = os.path.join(temp_folder, "slope_clipped.tif")

            translate_options = gdal.TranslateOptions(
                format="GTiff",
                projWin=window,
                projWinSRS=slope_crs.to_string(),
                outputSRS=slope_crs.to_string()
            )

            print(f"[INFO] Clipping slope map: {slope_map_path} to {clipped_slope_path}")
            ds_slope = gdal.Translate(clipped_slope_path, slope_map_path, options=translate_options)

            if ds_slope is None:
                raise ValueError("Slope clipping failed, GDAL returned None.")

            # Step 2: Align slope map to flood raster
            aligned_slope_path = os.path.join(temp_folder, "slope_aligned.tif")

            warp_options = gdal.WarpOptions(
                format="GTiff",
                xRes=10,   # 10m resolution downscale from 1m
                yRes=10,   # 10m resolution downscale from 1m
                dstSRS=profile["crs"].to_string(),
                outputBounds=rasterio.transform.array_bounds(profile["height"], profile["width"], profile["transform"]),
                resampleAlg="average"  # or "bilinear" (average is good for slope)
            )

            ds_warp = gdal.Warp(aligned_slope_path, clipped_slope_path, options=warp_options)

            if ds_warp is None:
                raise ValueError("Slope alignment failed, GDAL Warp returned None.")

            slope_map = ds_warp.ReadAsArray()
            ds_warp = None

            # Apply slope masking
            flood_mask[slope_map > slope_threshold] = 0
            print("Slope masking applied.")

        except Exception as e:
            print("Slope masking skipped. Reason:", e)

        # Save flood mask
        profile.update(dtype=rasterio.uint8, count=1)
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(flood_mask, 1)

def run_s1():
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)

    geo_wkt = get_aoi_wkt()
    pre_files, post_files = [], []
    print(f"Flood date: {flood_date}")
    for file in sorted(glob.glob(os.path.join(s1_zip_folder, "*.zip"))):
        print(f"Processing file: {file}")
        date = extract_date_from_filename(os.path.basename(file))
        print(f"Extracted date: {date}")
        
        if not date:
            continue
        if date < flood_date:
            print(f"Adding to pre-flood files: {file}")
            pre_files.append(file)
        else:
            print(f"Adding to post-flood files: {file}")
            post_files.append(file)

    pre_proc = []
    for f in pre_files:
        out = preprocess(f, geo_wkt)
        if out:
            pre_proc.append(out)

    post_proc = []
    for f in post_files:
        out = preprocess(f, geo_wkt)
        if out:
            post_proc.append(out)

    if not pre_proc or not post_proc:
        print("[WARNING] Insufficient pre/post images")
        return

    pre_mosaic, _ = merge([rasterio.open(f) for f in pre_proc])
    post_mosaic, trans = merge([rasterio.open(f) for f in post_proc])
    profile = rasterio.open(post_proc[0]).profile
    profile.update({"height": post_mosaic.shape[1], "width": post_mosaic.shape[2], "transform": trans})

    pre_path = os.path.join(temp_folder, "pre_merged.tif")
    post_path = os.path.join(temp_folder, "post_merged.tif")
    with rasterio.open(pre_path, "w", **profile) as dst:
        dst.write(pre_mosaic)
    with rasterio.open(post_path, "w", **profile) as dst:
        dst.write(post_mosaic)

    detect_change(pre_path, post_path, s1_tiff)

    shutil.rmtree(temp_folder)
    print("[INFO] Final flood map ready at:", s1_tiff)

def run_from_temp():
    pre_proc = []
    post_proc = []

    for tif in sorted(glob(os.path.join(temp_folder, "*_preprocessed.tif"))):
        date = extract_date_from_filename(os.path.basename(tif))
        if not date:
            continue
        if date < flood_date:
            pre_proc.append(tif)
        else:
            post_proc.append(tif)

    if not pre_proc or not post_proc:
        print("[ERROR] Not enough pre/post TIFFs found in temp folder.")
        return

    pre_mosaic, _ = merge([rasterio.open(f) for f in pre_proc])
    post_mosaic, trans = merge([rasterio.open(f) for f in post_proc])
    profile = rasterio.open(post_proc[0]).profile
    profile.update({"height": post_mosaic.shape[1], "width": post_mosaic.shape[2], "transform": trans})

    pre_path = os.path.join(temp_folder, "pre_merged.tif")
    post_path = os.path.join(temp_folder, "post_merged.tif")
    with rasterio.open(pre_path, "w", **profile) as dst:
        dst.write(pre_mosaic)
    with rasterio.open(post_path, "w", **profile) as dst:
        dst.write(post_mosaic)

    detect_change(pre_path, post_path, s1_tiff)
    print("[INFO] Final flood map ready at:", s1_tiff)

################################## updated ##########################################
def combine_s1_s2(s1_tiff, s2_tiff, combined_tiff, combined_shp):

    print("Combining Sentinel-1 and Sentinel-2 masks...")

    try:
        # Always open S1 first
        with rasterio.open(s1_tiff) as s1:
            s1_data = s1.read(1)
            s1_nodata = s1.nodata if s1.nodata is not None else 0
            s1_valid = s1_data != s1_nodata
            s1_flood = s1_data > 0

            # Initialize combined with S1 flood mask as default
            combined = np.zeros_like(s1_data, dtype=np.uint8)
            s1_flood_mask = s1_valid & s1_flood
            combined[s1_flood_mask] = 255

            # If S2 is available → open and combine
            if os.path.exists(s2_tiff):
                print("Sentinel-2 mask found → combining with Sentinel-1")
                with rasterio.open(s2_tiff) as s2:
                    s2_data = s2.read(1)

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

                    s2_nodata = s2.nodata if s2.nodata is not None else 0
                    s2_valid = s2_aligned != s2_nodata
                    s2_flood = s2_aligned == 1
                    s2_flood_mask = s2_valid & s2_flood

                    # Combine both masks
                    combined[s2_flood_mask] = 255

            else:
                print("Sentinel-2 mask NOT found → using Sentinel-1 only")

            # Reproject to target CRS
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

            # Apply AOI + Lakes + Rivers masks
            aoi = load_aoi()
            lakes = load_lakes()
            rivers = load_rivers()
            if lakes is not None:
                aoi = gpd.overlay(aoi, lakes, how='difference')
            if rivers is not None:
                aoi = gpd.overlay(aoi, rivers, how='difference')

            # Save unclipped first
            with rasterio.open("/tmp/combined_unclipped.tif", "w", driver="GTiff",
                               height=height, width=width, count=1, dtype="uint8",
                               crs=target_crs, transform=transform, nodata=0) as tmp:
                tmp.write(combined_reprojected, 1)

            # Apply AOI mask (clipping)
            with rasterio.open("/tmp/combined_unclipped.tif") as tmp_src:
                clipped, out_transform = mask(tmp_src, aoi.geometry, crop=True, nodata=0)
                final_meta = tmp_src.meta.copy()
                final_meta.update({
                    "height": clipped.shape[1],
                    "width": clipped.shape[2],
                    "transform": out_transform
                })

            # Remove small objects + Morph smoothing
            labeled, num_features = label(clipped[0] == 255)
            sizes = np.bincount(labeled.ravel())
            small_mask = np.isin(labeled, np.where(sizes < noise_min_pixels)[0])
            cleaned = clipped[0].copy()
            cleaned[small_mask] = 0

            # Morph smoothing
            cleaned = binary_closing(
                binary_opening(cleaned > 0, structure=np.ones((2, 2))),
                structure=np.ones((2, 2))
            ).astype(np.uint8) * 255

            # Save final cleaned TIFF
            with rasterio.open(combined_tiff, "w", **final_meta) as dst:
                dst.write(cleaned, 1)

            # Save shapefile
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
#########################################
#updated metadata
def write_metadata(event_date, aoi_name="Unknown"):
    try:
        event_date = datetime.strptime(event_date, "%Y-%m-%d")
        start_window = (event_date - timedelta(days=7)).strftime("%Y-%m-%d")
        end_window = (event_date + timedelta(days=7)).strftime("%Y-%m-%d")

        metadata = {
            "aoi_name": aoi_name,
            "event_date": event_date,
            "image_window_start": start_window,
            "image_window_end": end_window,
            "sentinel1_used": Path(s1_tiff).exists(),
            "sentinel2_used": Path(s2_tiff).exists(),
            "s1_image_count": len(glob.glob(os.path.join(s1_zip_folder, "*.zip"))),
            "s2_pre_ndwi_count": len(glob.glob(os.path.join(s2_pre_flood_folder, "preprocess", "NDWI", "*.tif"))),
            "s2_post_ndwi_count": len(glob.glob(os.path.join(s2_post_flood_folder, "preprocess", "NDWI", "*.tif"))),
            "processed_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "output_tiff": combined_tiff,
            "output_shapefile": combined_shapefile
        }

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
####################################
def run_pipeline(event_date, aoi_name): #updated
    print("Starting Flood Mapping Pipeline")

    run_s1()
    print("Sentinel-1 processing complete.")
    run_s2()
    print("Sentinel-2 processing complete.")

    # Combine S1 + S2
    combine_s1_s2(
        s1_tiff,
        s2_tiff,
        combined_tiff,
        combined_shapefile
    )

    # Save summary
    write_metadata(event_date, aoi_name) #updated
    print("Pipeline complete.")
    
#updated command with aoi_name
## python main.py "{'s1PreFlood':'sentinel1_GRD_preflood','s1PostFlood':'sentinel1_GRD_postflood','s2PreFlood':'sentinel2_pre_flood','s2PostFlood':'sentinel2_post_flood','geomWKT':'POLYGON ((10.644988646837982 45.85539621678084, 10.644988646837982 46.06780100571985, 10.991744628283294 46.06780100571985, 10.991744628283294 45.85539621678084, 10.644988646837982 45.85539621678084))','aoi_name':'Trentino','slopeArtifact':'Slopes_TN','slopeFileName':'trentino_slope_map.tif','lakeShapeArtifactName':'Lakes_TN','lakeShapeFileName':'idrspacq.shp','riverShapeArtifactName':'Rivers_TN','riverShapeFileName':'cif_pta2022_v.shp','output':'test_nk','eventDate':'2020-10-02','targetCRS':'EPSG:25832','polarization':['VV','VH'],'dem_threshold':700,'slope_threshold':7,'noise_min_pixels':15,'river_buffer_meters':2}"

if __name__ == "__main__":

    global geo_wkt, target_crs, flood_date, proj4_text, polarization, dem_threshold, slope_threshold, noise_min_pixels
    global lakes_shapefile, combined_shapefile, combined_tiff, s1_tiff, s2_tiff, metadata_output_path, output_folder
    global temp_folder,before_flood,artifact_name,after_flood, s2_post_flood_files, s2_pre_flood_files, geometry, slope_map_path
    global rivers_shapefile, river_buffer_meters, slopeFileName, lakeShapeFileName, riverShapeFileName
    # Parse command line arguments    
    args = sys.argv[1].replace("'","\"")
    json_input = json.loads(args)
    project_name=os.environ["PROJECT_NAME"]
    s1PreFloodArtifactName = json_input['s1PreFlood'] # S1 pre flood
    s1PostFloodArtifactName = json_input['s1PostFlood'] # S1 post flood
    s2PostFloodArtifactName = json_input['s2PostFlood'] # S2 post flood
    s2PreFloodArtifactName = json_input['s2PreFlood'] # S2 pre flood
    slopeArtifactName = json_input['slopeArtifact'] # Slope aritfact "slope_map_path": os.path.join(BASE_DIR, "data", "slope", "trentino_slope_map.tif"),
    slopeFileName = json_input['slopeFileName'] # Slope file name
    lakeShapeArtifactName = json_input['lakeShapeArtifactName'] # Lake Shape artifact
    lakeShapeFileName = json_input['lakeShapeFileName'] # Lake Shape file name
    riverShapeArtifactName = json_input['riverShapeArtifactName'] # Rivers Shape artifact
    riverShapeFileName = json_input['riverShapeFileName'] # Rivers Shape file name
    outputArtifactName = json_input['output'] # Output artifact name
    geo_wkt = json_input['geomWKT'] # AOI geometry in WKT format
    target_crs = json_input['targetCRS'] # "EPSG:25832"
    polarization = json_input['polarization'] # polarization (VV or VH) for both ["VV", "VH"]
    dem_threshold = json_input['dem_threshold'] # dem_threshold (500-1000)
    slope_threshold = json_input['slope_threshold'] # slope_threshold (7- 15)
    noise_min_pixels = json_input['noise_min_pixels'] # noise_min_pixels more than 10
    river_buffer_meters = json_input['river_buffer_meters'] # river_buffer_meters 1-2
    event_date = json_input['eventDate']  # updated 
    aoi_name = json_input.get('aoi_name', "Unknown")  # if no mention in input then "Unknown" #updated line

    BASE_DIR = '.'
    # Input folders
    s1_zip_folder = os.path.join(BASE_DIR, "data", "sentinel_zips")
    s2_pre_flood_folder = os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(Pre)")
    s2_post_flood_folder = os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(post)")
    slope_map_path = os.path.join(BASE_DIR, "data", "Slopes_TN", slopeFileName) # "trentino_slope_map.tif"
    lakes_shapefile = os.path.join(BASE_DIR, "data", "Lakes_TN", lakeShapeFileName) # "Lakes_TN", "idrspacq.shp"
    rivers_shapefile = os.path.join(BASE_DIR, "data", "Rivers_TN", riverShapeFileName) # "Rivers_TN", "cif_pta2022_v.shp"

    # Output folder (everything goes here)
    output_folder = os.path.join(BASE_DIR, "data", "flood_outputs")
    temp_folder = os.path.join(BASE_DIR, "data", "flood_outputs", "temp")  # Added temp folder
 

    # Output files
    s1_tiff = os.path.join(BASE_DIR, "data", "flood_outputs", "S1-flood_layer.tif")
    s2_tiff = os.path.join(BASE_DIR, "data", "flood_outputs", "S2-flood_layer.tif")
    combined_tiff = os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer.tif")
    combined_shapefile = os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer.shp")
    metadata_output_path = os.path.join(BASE_DIR, "data", "flood_outputs", "flood_detection_layer_metadata.json")

    # Make sure required folders exist
    os.makedirs(s1_zip_folder, exist_ok=True)
    os.makedirs(s2_post_flood_folder, exist_ok=True)
    os.makedirs(s2_pre_flood_folder, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", "Slopes_TN"), exist_ok=True) # "trentino_slope_map.tif" //folder name must be same as artifact name
    os.makedirs(os.path.join(BASE_DIR, "data", "Lakes_TN"), exist_ok=True)  # Ensure Lakes folder exists
    os.makedirs(os.path.join(BASE_DIR, "data", "Rivers_TN"), exist_ok=True)  # Ensure Rivers folder exists
    # Ensure output folders exist
    os.makedirs(output_folder, exist_ok=True)
    # Ensure temp folder exists
    os.makedirs(temp_folder, exist_ok=True)

    
    project = dh.get_or_create_project(project_name)
  
    # Download Sentinel-1 and Sentinel-2 artifacts
    print(f"Downloading Sentinel-1 pre-flood artifact for project: {project_name} Name: {s1PreFloodArtifactName}")
    sentinel1_preflood_artifact = project.get_artifact(s1PreFloodArtifactName)
    sentinel1_zip_path = sentinel1_preflood_artifact.download(s1_zip_folder, overwrite=True)
    print(f"Downloading Sentinel-1 post-flood artifact for project: {project_name} Name: {s1PostFloodArtifactName}")
    sentinel1_postflood_artifact = project.get_artifact(s1PostFloodArtifactName)
    sentinel1_zip_path = sentinel1_postflood_artifact.download(s1_zip_folder, overwrite=True)
    print(f"Downloading Sentinel-2 post-flood artifact for project: {project_name} Name: {s2PostFloodArtifactName}")
    sentinel2_postflood_artifact = project.get_artifact(s2PostFloodArtifactName)
    sentinel2_zip_path2 = sentinel2_postflood_artifact.download(s2_post_flood_folder, overwrite=True)
    print(f"Downloading Sentinel-2 pre-flood artifact for project: {project_name} Name: {s2PreFloodArtifactName}")
    sentinel2_preflood_artifact = project.get_artifact(s2PreFloodArtifactName)
    sentinel2_zip_path1 = sentinel2_preflood_artifact.download(s2_pre_flood_folder, overwrite=True)

    # Download Shapes & Slopes artifacts
    print(f"Downloading slope artifact for project: {project_name} Name: {slopeArtifactName}")
    slope_artifact = project.get_artifact(slopeArtifactName)
    slope_path =  slope_artifact.download(os.path.join(BASE_DIR, "data", "Slopes_TN"), overwrite=True)
    print(f"Downloading lake shape artifact for project: {project_name} Name: {lakeShapeArtifactName}")
    lake_artifact = project.get_artifact(lakeShapeArtifactName)
    lake_shp_path = lake_artifact.download(os.path.join(BASE_DIR, "data", "Lakes_TN"), overwrite=True)
    print(f"Downloading River artifacts for project: {project_name} Name: {riverShapeArtifactName}")
    rivers_artifact = project.get_artifact(riverShapeArtifactName)
    rivers_shp_path = rivers_artifact.download(os.path.join(BASE_DIR, "data", "Rivers_TN"), overwrite=True)

    flood_date = datetime.strptime(event_date, "%Y-%m-%d") # "2020-10-02"
    print(f"Flood Date: {flood_date}")
    print(f"AOI Name: {aoi_name}")
    

    s2_pre_flood_files = sorted(glob.glob(os.path.join(s2_pre_flood_folder, "preprocess", "NDWI", "*.tif")))
    s2_post_flood_files = sorted(glob.glob(os.path.join(s2_post_flood_folder, "preprocess", "NDWI", "*.tif")))

    print (f"Found {len(s2_pre_flood_files)} pre-flood NDWI files and {len(s2_post_flood_files)} post-flood NDWI files.")


    # --- Check if data is available ---
    if not s2_pre_flood_files or not s2_post_flood_files:
        print("No Sentinel-2 data available for flood detection. Skipping processing.")
    # else:
        # reproject_geometry(geom, src_crs, dst_crs)
        
    proj4_text = 'PROJCS["ETRS89 / UTM zone 32N", GEOGCS["ETRS89", DATUM["European Terrestrial Reference System 1989", SPHEROID["GRS 1980",6378137.0, 298.257222101]], PRIMEM["Greenwich", 0.0], UNIT["degree", 0.017453292519943295]], PROJECTION["Transverse_Mercator"], PARAMETER["central_meridian", 9.0], PARAMETER["latitude_of_origin", 0.0], PARAMETER["scale_factor", 0.9996], PARAMETER["false_easting", 500000.0], PARAMETER["false_northing", 0.0], UNIT["m", 1.0], AXIS["Easting", EAST], AXIS["Northing", NORTH], AUTHORITY["EPSG","25832"]]'

    run_pipeline(event_date, aoi_name) #updated

    #upload output artifact
    print(f"Uploading artifact: {outputArtifactName}") 
    zip_file = os.path.join(output_folder, outputArtifactName + '.zip')
    print(f"Creating zip file: {zip_file}")
    zf = zipfile.ZipFile(zip_file, "w")
    for dirname, subdirs, files in os.walk(output_folder):
        for filename in files:
            if(filename.endswith('flood_detection_layer.tif') or
                filename.endswith('flood_detection_layer_metadata.json') or
                filename.endswith('flood_detection_layer.shp')):
                print(f"Adding {filename} to the zip file")
                zf.write(os.path.join(dirname, filename), arcname=filename)
    zf.close()
    upload_artifact(artifact_name=outputArtifactName,project_name=project_name,src_path=zip_file)
    print("Flood mapping pipeline completed successfully.")