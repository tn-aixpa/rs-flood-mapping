import os
import datetime
import rasterio
import rasterio.mask
import geopandas as gpd
from shapely.wkt import loads
from shapely.geometry import shape
from rasterio.merge import merge
from glob import glob
from snapista import Graph, Operator
import logging
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from scipy.ndimage import label
import numpy as np
from scipy.ndimage import gaussian_gradient_magnitude

# === Import shared config ===
from config import CONFIG

# --- Logging Setup ---
os.makedirs(CONFIG["output_folder"], exist_ok=True)
log_path = os.path.join(CONFIG["output_folder"], "processing.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(log_path), logging.StreamHandler()]
)
logger = logging.getLogger()

# --- Derived values from CONFIG ---
S1_ZIP_PATH = CONFIG["s1_zip_folder"]
ZIP_FILES = glob(os.path.join(S1_ZIP_PATH, "*.zip"))
SHAPEFILE_PATH = CONFIG["shapefile_path"]
OUTPUT_TIFF_PATH = CONFIG["s1_tiff"]
TEMP_FOLDER = CONFIG["temp_folder"]
CROPPED_TIF_PATH = CONFIG["s1_tiff"]
FLOOD_DATE = CONFIG["flood_date"]
POLARIZATION = CONFIG["polarization"]
DEM_THRESHOLD = CONFIG["dem_threshold"]
SLOPE_THRESHOLD = CONFIG["slope_threshold"]
NOISE_MIN_PIXELS = CONFIG["noise_min_pixels"]

# === Ensure folders exist ===
os.makedirs(TEMP_FOLDER, exist_ok=True)


# Validate paths
logging.info("Validating input paths...")
if not os.path.exists(S1_ZIP_PATH):
    logging.error(f"Sentinel-1 directory not found: {S1_ZIP_PATH}")
    raise FileNotFoundError(f"Sentinel-1 directory not found: {S1_ZIP_PATH}")
if not ZIP_FILES:
    logging.error(f"No ZIP files found in {S1_ZIP_PATH}")
    raise FileNotFoundError(f"No ZIP files found in {S1_ZIP_PATH}")
if not os.path.exists(SHAPEFILE_PATH):
    logging.error(f"Shapefile not found: {SHAPEFILE_PATH}")
    raise FileNotFoundError(f"Shapefile not found: {SHAPEFILE_PATH}")


def extract_date_from_filename(filename):
    try:
        parts = filename.split('_')
        date_str = parts[4][:8]
        return datetime.datetime.strptime(date_str, "%Y%m%d")
    except Exception as e:
        logging.error(f"Failed to extract date from {filename}: {str(e)}")
        return None

def get_aoi_wkt_and_projection():
    try:
        gdf = gpd.read_file(SHAPEFILE_PATH)
        gdf = gdf.to_crs(epsg=4326)
        aoi_geom = gdf.geometry.union_all()
        logging.info("AOI converted to WKT with CRS EPSG:4326")
        return aoi_geom.wkt, gdf.crs
    except Exception as e:
        logging.error(f"Failed to process shapefile {SHAPEFILE_PATH}: {str(e)}")
        raise

def check_aoi_overlap(zip_path, aoi_wkt):
    logging.info(f"DEBUG: Using manifest.safe for {zip_path}")
    try:
        if not isinstance(aoi_wkt, str):
            logging.error(f"Invalid aoi_wkt type: {type(aoi_wkt)}")
            return False
        with zipfile.ZipFile(zip_path, 'r') as z:
            manifest_path = [f for f in z.namelist() if f.endswith('manifest.safe')][0]
            logging.info(f"Found manifest: {manifest_path}")
            with z.open(manifest_path) as f:
                manifest_content = f.read()
        root = ET.parse(BytesIO(manifest_content)).getroot()
        footprint = None
        for coordinates in root.findall(".//gml:coordinates", namespaces={'gml': 'http://www.opengis.net/gml'}):
            coords = coordinates.text.strip().split()
            logging.info(f"Coordinates: {coords[:5]}...")
            coords = [tuple(map(float, c.split(','))) for c in coords]
            footprint = shape({
                'type': 'Polygon',
                'coordinates': [[(lon, lat) for lat, lon in coords]]
            })
            break
        if not footprint:
            logging.error(f"No footprint found in manifest for {zip_path}")
            return False
        gdf_footprint = gpd.GeoDataFrame(geometry=[footprint], crs="EPSG:4326")
        aoi = loads(aoi_wkt)
        intersects = gdf_footprint.geometry.iloc[0].intersects(aoi)
        logging.info(f"AOI overlap check for {zip_path}: {'Success' if intersects else 'No overlap'}")
        return intersects
    except Exception as e:
        logging.error(f"Failed to check AOI overlap for {zip_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

PROJ4_TEXT = 'PROJCS["ETRS89 / UTM zone 32N", GEOGCS["ETRS89", DATUM["European Terrestrial Reference System 1989", SPHEROID["GRS 1980",6378137.0, 298.257222101, AUTHORITY["EPSG","7019"]], TOWGS84[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], AUTHORITY["EPSG","6258"]], PRIMEM["Greenwich", 0.0, AUTHORITY["EPSG","8901"]], UNIT["degree", 0.017453292519943295], AXIS["Geodetic longitude", EAST], AXIS["Geodetic latitude", NORTH], AUTHORITY["EPSG","4258"]], PROJECTION["Transverse_Mercator", AUTHORITY["EPSG","9807"]], PARAMETER["central_meridian", 9.0], PARAMETER["latitude_of_origin", 0.0], PARAMETER["scale_factor", 0.9996], PARAMETER["false_easting", 500000.0], PARAMETER["false_northing", 0.0], UNIT["m", 1.0], AXIS["Easting", EAST], AXIS["Northing", NORTH], AUTHORITY["EPSG","25832"]]'

def preprocess_and_subset(zip_path, geo_wkt):
    out_file = os.path.join(TEMP_FOLDER, os.path.basename(zip_path).replace(".zip", "_preprocessed.tif"))
    try:
        if not os.path.exists(zip_path):
            logging.error(f"ZIP file not found: {zip_path}")
            return None
        if not check_aoi_overlap(zip_path, geo_wkt):
            logging.info(f"Skipping {zip_path}: No AOI overlap")
            return None
        g = Graph()
        g.add_node(Operator("Read", file=zip_path, formatName="SENTINEL-1"), node_id="read")
        g.add_node(Operator("Apply-Orbit-File", orbitType="Sentinel Precise (Auto Download)", continueOnFail="true"), node_id="orbit", source="read")
        g.add_node(Operator("Calibration", outputSigmaBand="true", outputImageScaleInDb="false", selectedPolarisations=POLARIZATION), node_id="calibration", source="orbit")
        g.add_node(Operator("Speckle-Filter", filter="Lee", filterSizeX="5", filterSizeY="5"), node_id="speckle", source="calibration")
        g.add_node(Operator("Subset", geoRegion=geo_wkt), node_id="subset", source="speckle")
        g.add_node(Operator("Terrain-Correction", demName="SRTM 3Sec", pixelSpacingInMeter="10.0", mapProjection=PROJ4_TEXT), node_id="tc", source="subset")
        g.add_node(Operator("Write", file=out_file, formatName="GeoTIFF-BigTIFF"), node_id="write", source="tc")
        g.run()
        if not os.path.exists(out_file):
            logging.error(f"Output file not created: {out_file}")
            return None
        logging.info(f"Preprocessed file saved to {out_file}")
        return out_file
    except Exception as e:
        logging.error(f"Error preprocessing {zip_path}: {str(e)}")
        return None

def detect_flood(input_raster, output_path):
    try:
        with rasterio.open(input_raster) as src:
            band = src.read(1)
            elevation = src.read(2) if src.count > 1 else None
            profile = src.profile

            flood_mask = (band < 1.13E-2).astype(np.uint8)
            if elevation is not None:
                flood_mask[elevation > DEM_THRESHOLD] = 0
                slope = np.degrees(np.arctan(gaussian_gradient_magnitude(elevation, sigma=1)))
                flood_mask[slope > SLOPE_THRESHOLD] = 0

            structure = np.ones((3, 3), dtype=int)
            labeled, num_features = label(flood_mask, structure=structure)
            counts = np.bincount(labeled.ravel())
            remove_labels = np.where(counts < NOISE_MIN_PIXELS)[0]
            mask = np.isin(labeled, remove_labels)
            flood_mask[mask] = 0

        profile.update(dtype=rasterio.uint8, count=1)
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(flood_mask, 1)
        logging.info(f"Flood detection result saved to {output_path}")
    except Exception as e:
        logging.error(f"Error in flood detection for {input_raster}: {str(e)}")
        raise

def batch_process():
    try:
        geo_wkt, target_crs = get_aoi_wkt_and_projection()
        processed_rasters = []
        if not ZIP_FILES:
            logging.error(f"No ZIP files found in {S1_ZIP_PATH}")
            print(f"[ERROR] No ZIP files found in {S1_ZIP_PATH}")
            return
        for file in sorted(ZIP_FILES):
            file_name = os.path.basename(file)
            file_date = extract_date_from_filename(file_name)
            if file_date and file_date >= FLOOD_DATE:
                logging.info(f"Processing {file_name}")
                print(f"[INFO] Preprocessing and subsetting {file_name}")
                result = preprocess_and_subset(file, geo_wkt)
                if result:
                    processed_rasters.append(result)
            else:
                logging.info(f"Skipping {file_name}: Date {file_date} not after {FLOOD_DATE}")
                print(f"[INFO] Skipping {file_name}: Date {file_date} not after {FLOOD_DATE}")
        if not processed_rasters:
            logging.error("No usable preprocessed rasters found")
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
        logging.info(f"Merged cropped raster saved to {merged_path}")
        print(f"[INFO] Merged cropped raster saved to {merged_path}")
        detect_flood(merged_path, CROPPED_TIF_PATH)
        for temp in processed_rasters:
            if os.path.exists(temp):
                os.remove(temp)
        if os.path.exists(merged_path):
            os.remove(merged_path)
        logging.info("Cleanup complete. Final flood map ready")
        print("[INFO] Cleanup complete. Final flood map ready.")
    except Exception as e:
        logging.error(f"Batch processing failed: {str(e)}")
        print(f"[ERROR] Batch processing failed: {str(e)}")

if __name__ == "__main__":
    batch_process()
