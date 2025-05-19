import os
from glob import glob

# Automatically get the path to this config file's folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# === Input Sentinel-1 ZIP ===
S1_ZIP_PATH = os.path.join(BASE_DIR, "data", "sentinel_zips", "S1B_IW_GRDH_1SDV_20201003T052640_20201003T052705_023644_02CEC7_E20C.SAFE.zip")
ZIP_FILES = [S1_ZIP_PATH]  # Keep it a list for compatibility

# === Optional: For batch processing instead ===
# ZIP_FOLDER = os.path.join(BASE_DIR, "data", "sentinel_zips")
# ZIP_FILES = glob(os.path.join(ZIP_FOLDER, "*.zip"))

# === Output path (used as base for export) ===
OUTPUT_PATH = os.path.join(BASE_DIR, "data", "final_mask")

# === Date & Settings ===
FLOOD_DATE = "2020-10-02"
POLARIZATION = "VV"

# === Shapefile and Output Directory ===
SHAPEFILE_PATH = os.path.join(BASE_DIR, "data", "AOI_Rec.shp")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "data", "flood_outputs")

# Ensure output folder exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)



