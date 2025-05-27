import os
import glob
import json
import logging
from datetime import datetime
from pathlib import Path
import numpy as np
import rasterio
from rasterio.mask import mask
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
from config import CONFIG

# Setup
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/flood_pipeline.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def load_aoi():
    aoi_path = CONFIG["shapefile_path"]
    gdf = gpd.read_file(aoi_path)
    if not gdf.crs:
        gdf.set_crs(CONFIG["target_crs"], inplace=True)
    elif gdf.crs.to_string() != CONFIG["target_crs"]:
        gdf = gdf.to_crs(CONFIG["target_crs"])
    return gdf

def load_lakes():
    lakes_path = CONFIG.get("lakes_shapefile")
    if not lakes_path or not os.path.exists(lakes_path):
        logging.warning("Lakes shapefile not found or not configured.")
        return None
    lakes = gpd.read_file(lakes_path)
    lakes = lakes.to_crs(CONFIG["target_crs"])
    return lakes

def compute_mean_ndwi(files, aoi_gdf):
    stack = []
    nodata_val = -9999.0
    ref_crs = CONFIG["target_crs"]
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
                logging.warning(f"Skipping {f}: no AOI overlap")

    if not stack:
        raise ValueError("No valid NDWI files found.")
    return np.nanmean(np.stack(stack), axis=0), transform, ref_crs, height, width

def save_s2_flood_layer(ndwi, transform, crs, height, width, threshold, raster_out):
    mask_out = (ndwi > threshold).astype(np.uint8)
    with rasterio.open(raster_out, "w", driver="GTiff", height=height, width=width,
                       count=1, dtype="uint8", crs=crs, transform=transform, nodata=0) as dst:
        dst.write(mask_out, 1)
    logging.info(f"Saved S2 flood mask: {raster_out}")

def combine_s1_s2(s1_path, s2_path, combined_tiff, combined_shp):
    logging.info("Combining Sentinel-1 and Sentinel-2 masks...")
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
                s1.crs, CONFIG["target_crs"], s1.width, s1.height, *s1.bounds
            )
            combined_reprojected = np.zeros((height, width), dtype=np.uint8)

            reproject(
                source=combined,
                destination=combined_reprojected,
                src_transform=s1.transform,
                src_crs=s1.crs,
                dst_transform=transform,
                dst_crs=CONFIG["target_crs"],
                resampling=Resampling.nearest
            )

            aoi = load_aoi()
            lakes = load_lakes()

            if lakes is not None:
                aoi = gpd.overlay(aoi, lakes, how='difference')

            with rasterio.open("/tmp/combined_unclipped.tif", "w", driver="GTiff",
                               height=height, width=width, count=1, dtype="uint8",
                               crs=CONFIG["target_crs"], transform=transform, nodata=0) as tmp:
                tmp.write(combined_reprojected, 1)

            with rasterio.open("/tmp/combined_unclipped.tif") as tmp_src:
                clipped, out_transform = mask(tmp_src, aoi.geometry, crop=True, nodata=0)
                final_meta = tmp_src.meta.copy()
                final_meta.update({
                    "height": clipped.shape[1],
                    "width": clipped.shape[2],
                    "transform": out_transform
                })

            with rasterio.open(combined_tiff, "w", **final_meta) as dst:
                dst.write(clipped)

            results = shapes(clipped[0], mask=clipped[0] == 255, transform=out_transform)
            geoms = [shape(g) for g, _ in results]
            if geoms:
                gdf = gpd.GeoDataFrame({"geometry": geoms}, crs=CONFIG["target_crs"])
                gdf.to_file(combined_shp)

            logging.info(f"Final combined TIFF: {combined_tiff}")
            logging.info(f"Final vector: {combined_shp}")

    except Exception as e:
        logging.error(f"Fusion failed: {e}")
        raise

def write_metadata():
    try:
        metadata = {
            "aoi_name": CONFIG.get("aoi_name", "Unknown"),
            "flood_period": {
                "before": " to ".join(CONFIG.get("before_flood", ["?", "?"])),
                "after": " to ".join(CONFIG.get("after_flood", ["?", "?"]))
            },
            "sentinel1_used": Path(CONFIG["s1_tiff"]).exists(),
            "sentinel2_used": Path(CONFIG["s2_tiff"]).exists(),
            "s1_image_count": len(glob.glob(os.path.join(CONFIG["s1_zip_folder"], "*.zip"))),
            "s2_pre_ndwi_count": len(glob.glob(os.path.join(CONFIG["s2_pre_ndwi_folder"], "*.tif"))),
            "s2_post_ndwi_count": len(glob.glob(os.path.join(CONFIG["s2_post_ndwi_folder"], "*.tif"))),
            "processed_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "output_tiff": CONFIG["combined_tiff"],
            "output_shapefile": CONFIG["combined_shapefile"]
        }

        # Compute total flood area in sq. km if shapefile exists
        shp = CONFIG["combined_shapefile"]
        if Path(shp).exists():
            gdf = gpd.read_file(shp)
            if gdf.crs.is_geographic:
                gdf = gdf.to_crs(CONFIG["target_crs"])
            metadata["total_flooded_area_sqkm"] = round(gdf.geometry.area.sum() / 1e6, 2)
        else:
            metadata["total_flooded_area_sqkm"] = "Not computed"

        with open(CONFIG["metadata_output_path"], "w") as f:
            json.dump(metadata, f, indent=4)

        logging.info("Metadata saved with image counts and flood area.")
    except Exception as e:
        logging.error(f"Failed to write metadata: {e}")


def run_pipeline():
    logging.info("Starting Flood Mapping Pipeline")
    aoi = load_aoi()

    ndwi_post, transform, crs, height, width = compute_mean_ndwi(
        glob.glob(os.path.join(CONFIG["s2_post_ndwi_folder"], "*.tif")), aoi
    )
    save_s2_flood_layer(
        ndwi_post, transform, crs, height, width, threshold=0.0,
        raster_out=CONFIG["s2_tiff"]
    )

    from sentinel_1_processing import batch_process
    batch_process()

    combine_s1_s2(CONFIG["s1_tiff"], CONFIG["s2_tiff"],
                  CONFIG["combined_tiff"], CONFIG["combined_shapefile"])

    write_metadata()
    logging.info("Pipeline complete.")

if __name__ == "__main__":
    run_pipeline()


