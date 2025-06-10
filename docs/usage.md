# RS-Flood-Mapping

## Usage Scenario

This tool provides a streamlined approach to detect floods using Sentinel-1 and Sentinel-2 data, as well as rainfall analysis using CHIRPS data. Below are the steps to use the project. It performs the flood analysis based on event date (for e.g 10-02-2020). This project implements a pipeline for flood using Sentinel-1 and Sentinel-2 imagery over a time window pre and post the flood event date. It processes raw .SAFE or .zip Sentinel-2 inputs, extracts extracts NDWI indices, detect water bodies before and after a flood event, and outputs change detection and probability maps.

## Input

- **Sentinel-1 L2A Data** in `.SAFE` folders or `.zip` format.
- **Sentinel-2 L2A Data** in `.SAFE` folders or `.zip` format.
- **Lake shapes** in `Lakes_TN` folder in '.shp' format
- **River shapes** in `Rivers_TN` folder in '.shp' format
- **Slope shapes** in `Slopes_TN` folder in '.shp' format

## Output

GeoTIFF file for:

- **raster and vector outputs** (e.g., `output_flood_mask.tif`)
