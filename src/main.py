
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


    # --- NDWI MEAN COMPUTATION ---
def compute_mean_ndwi(files, geometry, fill_value=0.0):
    ndwi_stack = []
    ref_shape = None
    ref_transform = None
    ref_crs = None

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
                else:
                    if ndwi.shape != ref_shape:
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
            raise ValueError("No valid NDWI rasters found for AOI.")

        ndwi_stack = np.array(ndwi_stack)
        mean_ndwi = np.mean(ndwi_stack, axis=0)
        return mean_ndwi, ref_transform, ref_crs

    # --- PROCESS NDWI ---
    ndwi_pre, pre_transform, pre_crs = compute_mean_ndwi(pre_flood_files, geometry)
    ndwi_post, post_transform, post_crs = compute_mean_ndwi(post_flood_files, geometry)
    ndwi_diff = ndwi_post - ndwi_pre

    # --- FLOOD DETECTION ---
    ndwi_threshold = 0.2     # NDWI > 0.2 generally indicates surface water (typical range: 0.2–0.3)
    change_threshold = 0.1   # ΔNDWI > 0.1 indicates new water appearance (typical range: 0.05–0.2)

    pre_water = ndwi_pre > ndwi_threshold
    post_water = ndwi_post > ndwi_threshold
    new_water = (post_water.astype(int) - pre_water.astype(int)) == 1
    flood_pixels = (ndwi_diff > change_threshold) & new_water

    # --- SAVE FLOOD MASK AS TIFF ---
    def save_flood_mask_tiff(flood_array, transform, crs, output_path, nodata=0):
        """Save binary flood mask to GeoTIFF."""
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

        # --- Save output ---
        output_tiff_path = os.path.join(output_folder, "S2-flood_layer.tif")
        save_flood_mask_tiff(flood_pixels, post_transform, post_crs, output_tiff_path)


########################FILE 2#########################################33
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

def detect_change(pre_path, post_path, output_path):
    with rasterio.open(pre_path) as pre, rasterio.open(post_path) as post:
        profile = post.profile
        pre_band = pre.read(1).astype(np.float32)
        post_band = post.read(1).astype(np.float32)
        pre_band[pre_band == 0] = np.nan
        post_band[post_band == 0] = np.nan
        diff = post_band - pre_band
        flood_mask = (diff < -0.01).astype(np.uint8)

        try:
            with rasterio.open(slope_map_path) as slope_src:
                slope_data = slope_src.read(1).astype(np.float32)
                reprojected = np.empty_like(flood_mask, dtype=np.float32)
                reproject(
                    source=slope_data,
                    destination=reprojected,
                    src_transform=slope_src.transform,
                    src_crs=slope_src.crs,
                    dst_transform=profile["transform"],
                    dst_crs=profile["crs"],
                    resampling=Resampling.bilinear
                )
                flood_mask[reprojected > slope_threshold] = 0
                print("Slope masking applied.")
        except Exception as e:
            print("Slope masking skipped. Reason:", e)
        # except:
        #     pass

        profile.update(dtype=rasterio.uint8, count=1)
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(flood_mask, 1)

def run():
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

    detect_change(pre_path, post_path, output_tiff_path)

    shutil.rmtree(temp_folder)
    print("[INFO] Final flood map ready at:", output_tiff_path)

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

    detect_change(pre_path, post_path, output_tiff_path)
    print("[INFO] Final flood map ready at:", output_tiff_path)


################################## FILE 3 ##########################################

def combine_s1_s2(s1_path, s2_path, combined_tiff, combined_shp):
    print("Combining Sentinel-1 and Sentinel-2 masks...")
    try:
        with rasterio.open(s1_path) as s1, rasterio.open(s2_path) as s2:
            s1_data = s1.read(1)
            s2_data = s2.read(1)  
            s1_nodata = s1.nodata if s1.nodata is not None else 0
            s1_valid = s1_data != s1_nodata
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


            s2_nodata = s2.nodata if s2.nodata is not None else 0
            s2_valid = s2_aligned != s2_nodata
            s2_flood = s2_aligned == 1


            combined = np.zeros_like(s1_data, dtype=np.uint8)
        # Detect flood pixels
            s1_flood_mask = s1_valid & s1_flood
            s2_flood_mask = s2_valid & s2_flood

        # Combine flood detections
            combined = np.zeros_like(s1_data, dtype=np.uint8)
            combined[s1_flood_mask | s2_flood_mask] = 255

        # Mask where both have no valid data
            combined[~(s1_valid | s2_valid)] = 0


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
                dst_crs= target_crs,
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
                               crs= target_crs, transform=transform, nodata=0) as tmp:
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
###################################################################
def write_metadata():
    try:
        metadata = {
            "aoi_name": "Unknown",
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

def run_pipeline():
    print("Starting Flood Mapping Pipeline")

    run()

    # Combine S1 + S2
    combine_s1_s2(
        s1_tiff,
        s2_tiff,
        combined_tiff,
        combined_shapefile
    )

    # Save summary
    write_metadata()
    print("Pipeline complete.")
    

def reproject_geometry(geom, src_crs, dst_crs):
    if src_crs != dst_crs:
        project = pyproj.Transformer.from_crs(src_crs, dst_crs, always_xy=True).transform
        return transform(project, geom)
    return geom

## python main.py "{'s1PreFlood':'sentinel1_GRD_preflood','s1PostFlood':'sentinel1_GRD_postflood','s2PreFlood':'sentinel2_pre_flood','s2PostFlood':'sentinel2_post_flood','geomWKT':'POLYGON ((10.644988646837982 45.85539621678084, 10.644988646837982 46.06780100571985, 10.991744628283294 46.06780100571985, 10.991744628283294 45.85539621678084, 10.644988646837982 45.85539621678084))','slopeArtifact':'Slope_TN','slopeFileName':'slope_map25832.tif','lakeShapeArtifactName':'Lakes_TN','lakeShapeFileName':'idrspacq.shp','riverShapeArtifactName':'Rivers_TN','riverShapeFileName':'cif_pta2022_v.shp','output':'test_nk','eventDate':'2020/10/02','targetCRS':'EPSG:25832','polarization':'VV','dem_threshold':200,'slope_threshold':5,'noise_min_pixels':5,'river_buffer_meters':2}"

if __name__ == "__main__":

    global geo_wkt, target_crs, flood_date, proj4_text, polarization, dem_threshold, slope_threshold, noise_min_pixels
    global lakes_shapefile, combined_shapefile, combined_tiff, s1_tiff, s2_tiff, metadata_output_path, output_folder
    global temp_folder,before_flood,artifact_name,after_flood, pre_flood_files, post_flood_files, geometry, slope_map_path
    global rivers_shapefile, river_buffer_meters
    # Parse command line arguments    
    args = sys.argv[1].replace("'","\"")
    json_input = json.loads(args)
    project_name=os.environ["PROJECT_NAME"]
    s1PreFloodArtifactName = json_input['s1PreFlood'] # S1 pre flood
    s1PostFloodArtifactName = json_input['s1PostFlood'] # S1 post flood
    s2PostFloodArtifactName = json_input['s2PostFlood'] # S2 post flood
    s2PreFloodArtifactName = json_input['s2PreFlood'] # S2 pre flood
    slopeArtifactName = json_input['slopeArtifact'] # Slope aritfact "slope_map_path": os.path.join(BASE_DIR, "data", "slope", "slope_map25832.tif"),
    slopeFileName = json_input['slopeFileName'] # Slope file name
    lakeShapeArtifactName = json_input['lakeShapeArtifactName'] # Lake Shape artifact
    lakeShapeFileName = json_input['lakeShapeFileName'] # Lake Shape file name
    riverShapeArtifactName = json_input['riverShapeArtifactName'] # Rivers Shape artifact
    riverShapeFileName = json_input['riverShapeFileName'] # Rivers Shape file name
    outputArtifactName = json_input['output'] # Output artifact name
    floodDate = json_input['eventDate'] # flood date
    geo_wkt = json_input['geomWKT'] # AOI geometry in WKT format
    target_crs = json_input['targetCRS'] # "EPSG:25832"
    polarization = json_input['polarization'] # polarization (VV or VH)
    dem_threshold = json_input['dem_threshold'] # dem_threshold (200-700)
    slope_threshold = json_input['slope_threshold'] # slope_threshold (5- 15)
    noise_min_pixels = json_input['noise_min_pixels'] # noise_min_pixels 5
    river_buffer_meters = json_input['river_buffer_meters'] # river_buffer_meters 2
    
    BASE_DIR = '.'
    # Input folders
    s1_zip_folder = os.path.join(BASE_DIR, "data", "sentinel_zips")
    s2_pre_flood_folder = os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(Pre)")
    s2_post_flood_folder = os.path.join(BASE_DIR, "data", "sentinel2", "Sentinel-2(post)")
    slope_map_path = os.path.join(BASE_DIR, "data", "Slopes_TN", slopeFileName) # "slope_map25832.tif"
    lakes_shapefile = os.path.join(BASE_DIR, "data", "Lakes_TN", lakeShapeFileName) # "Lakes_TN", "idrspacq.shp"
    rivers_shapefile = os.path.join(BASE_DIR, "data", "Rivers_TN", riverShapeFileName) # "Rivers_TN", "cif_pta2022_v.shp"

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
    os.makedirs(s2_post_flood_folder, exist_ok=True)
    os.makedirs(s2_pre_flood_folder, exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "data", "Slopes_TN"), exist_ok=True) # "slope_map25832.tif" //folder name must be same as artifact name
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
    print(f"Downloading slop artifact for project: {project_name} Name: {slopeArtifactName}")
    slope_artifact = project.get_artifact(slopeArtifactName)
    slope_path =  slope_artifact.download(os.path.join(BASE_DIR, "data", "Slope_TN"), overwrite=True)
    print(f"Downloading lake shape artifact for project: {project_name} Name: {lakeShapeArtifactName}")
    lake_artifact = project.get_artifact(lakeShapeArtifactName)
    lake_shp_path = lake_artifact.download(os.path.join(BASE_DIR, "data", lakeShapeArtifactName), overwrite=True)
    print(f"Downloading River artifacts for project: {project_name} Name: {riverShapeArtifactName}")
    rivers_artifact = project.get_artifact(riverShapeArtifactName)
    rivers_shp_path = rivers_artifact.download(os.path.join(BASE_DIR, "data", riverShapeArtifactName), overwrite=True)

    flood_date = datetime.strptime(floodDate, "%Y/%m/%d") # "20201002"
    print(f"flood date: {flood_date}")

    #S1_ZIP_PATH = s1_zip_folder
    #TEMP_FOLDER = temp_folder
    #OUTPUT_TIFF_PATH = s1_tiff
    #FLOOD_DATE = flood_date 
    #POLARIZATION = polarization
    #SLOPE_THRESHOLD = slope_threshold
    #SLOPE_MAP_PATH = slope_map_path  # Make sure slope_map_path is defined

    pre_flood_files = sorted(glob.glob(os.path.join(s2_pre_flood_folder, "preprocess", "NDWI", "*.tif")))
    post_flood_files = sorted(glob.glob(os.path.join(s2_post_flood_folder, "preprocess", "NDWI", "*.tif")))

    # --- Check if data is available ---
    if not pre_flood_files or not post_flood_files:
        print("No Sentinel-2 data available for flood detection. Skipping processing.")
    # else:
        # reproject_geometry(geom, src_crs, dst_crs)
        
    proj4_text = 'PROJCS["ETRS89 / UTM zone 32N", GEOGCS["ETRS89", DATUM["European Terrestrial Reference System 1989", SPHEROID["GRS 1980",6378137.0, 298.257222101]], PRIMEM["Greenwich", 0.0], UNIT["degree", 0.017453292519943295]], PROJECTION["Transverse_Mercator"], PARAMETER["central_meridian", 9.0], PARAMETER["latitude_of_origin", 0.0], PARAMETER["scale_factor", 0.9996], PARAMETER["false_easting", 500000.0], PARAMETER["false_northing", 0.0], UNIT["m", 1.0], AXIS["Easting", EAST], AXIS["Northing", NORTH], AUTHORITY["EPSG","25832"]]'

    run_pipeline()

    print(f"Uploading artifact: {outputArtifactName}") 
    upload_artifact(
        artifact_name=outputArtifactName,
        project_name=project_name,
        src_path=output_folder
    )
    print("Flood mapping pipeline completed successfully.")