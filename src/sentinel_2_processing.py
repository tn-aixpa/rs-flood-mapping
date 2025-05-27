import os
import glob
import logging
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.mask import mask
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_bounds
from config import CONFIG

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

def compute_mean_ndwi(files, aoi, target_crs, target_transform, width, height, nodata_val=-9999.0):
    stack = []
    for file in files:
        try:
            with rasterio.open(file) as src:
                aoi_proj = aoi.to_crs(src.crs)
                clipped, src_transform = mask(src, aoi_proj.geometry, crop=True, nodata=nodata_val)
                clipped = clipped[0]

                reprojected = np.full((height, width), nodata_val, dtype=np.float32)
                reproject(
                    source=clipped,
                    destination=reprojected,
                    src_transform=src_transform,
                    src_crs=src.crs,
                    dst_transform=target_transform,
                    dst_crs=target_crs,
                    resampling=Resampling.bilinear,
                    src_nodata=nodata_val,
                    dst_nodata=nodata_val
                )
                stack.append(reprojected)
        except Exception as e:
            logger.warning(f"Skipping {file}: {e}")
            continue

    if not stack:
        return None
    return np.nanmean(np.stack(stack), axis=0)

def run_s2_pipeline(pre_flood_folder, post_flood_folder, aoi_path, output_tiff_path, ndwi_threshold=0.15):
    try:
        logger.info(" Running Sentinel-2 flood processing...")

        pre_files = sorted(glob.glob(os.path.join(pre_flood_folder, "*.tif")))
        post_files = sorted(glob.glob(os.path.join(post_flood_folder, "*.tif")))

        if not pre_files or not post_files:
            logger.warning(" No Sentinel-2 NDWI images found.")
            return None

        aoi = gpd.read_file(aoi_path)
        target_crs = CONFIG["target_crs"]
        aoi = aoi.to_crs(target_crs)

        # Define a common output grid (based on AOI bounds and fixed 10m resolution)
        bounds = aoi.total_bounds  # [minx, miny, maxx, maxy]
        resolution = 10  # meters
        width = int((bounds[2] - bounds[0]) / resolution)
        height = int((bounds[3] - bounds[1]) / resolution)
        transform = from_bounds(*bounds, width, height)

        # Compute mean NDWI images
        ndwi_pre = compute_mean_ndwi(pre_files, aoi, target_crs, transform, width, height)
        ndwi_post = compute_mean_ndwi(post_files, aoi, target_crs, transform, width, height)

        if ndwi_pre is None or ndwi_post is None:
            logger.warning(" Insufficient data to compute NDWI difference.")
            return None

        # NDWI difference and thresholding
        ndwi_diff = ndwi_post - ndwi_pre
        flood_mask = (ndwi_diff > ndwi_threshold).astype(np.uint8)

        # Output metadata
        out_meta = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": "uint8",
            "crs": target_crs,
            "transform": transform,
            "nodata": 0
        }

        # Save flood mask as TIFF
        with rasterio.open(output_tiff_path, "w", **out_meta) as dst:
            dst.write(flood_mask, 1)

        logger.info(f" Sentinel-2 flood mask saved: {output_tiff_path}")
        return output_tiff_path

    except Exception as e:
        logger.error(f" Sentinel-2 processing error: {e}")
        return None

# === Optional CLI run ===
if __name__ == "__main__":
    run_s2_pipeline(
        CONFIG["s2_pre_ndwi_folder"],
        CONFIG["s2_post_ndwi_folder"],
        CONFIG["shapefile_path"],
        CONFIG["s2_tiff"]
    )
