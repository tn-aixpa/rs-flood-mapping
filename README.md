# Flood detection

- **Visualization and Analysis of Floods Using Earth Engine and Geemap**: This project focuses on leveraging satellite imagery and geospatial tools to detect and visualize flood-affected areas.

- **NDWI Calculation**: The notebook calculates the Normalized Difference Water Index (NDWI) using Sentinel-2 imagery to detect water bodies before and after a flood event.

- **Flood Detection**: Sentinel-1 SAR data is used to calculate flood extent by analyzing pre- and post-event backscatter differences.

- **Rainfall Analysis**: CHIRPS precipitation data is analyzed to understand rainfall trends and their relationship to flood events, with time-series and monthly rainfall summaries.

- **Post-Processing Steps**: This version of the code provides an initial estimation of flood detection but requires further post-processing steps to enhance accuracy. These include refining the thresholds, integrating auxiliary datasets, and improving water body masking, which are currently underway.

- **Outputs**:
  - Interactive maps showing pre-flood, post-flood, and flood-extent layers.
  - Monthly and annual precipitation analysis visualizations.
  - Identification and visualization of flood-affected areas with permanent water body masking.
- **Raster and vector outputs are saved to the specified Google Drive folder for further visualization and analysis in geospatial tools such as ArcGIS or QGIS.**


## Requirements
To follow this tutorial, you must first [sign up](https://code.earthengine.google.com/register) for a [Google Earth Engine account](https://earthengine.google.com/). Earth Engine is a cloud computing platform with a multi-petabyte catalog of satellite imagery and geospatial datasets. It is free for noncommercial use. To authenticate the Earth Engine Python API, see instructions [here](https://book.geemap.org/chapters/01_introduction.html#earth-engine-authentication).

In this tutorial, we will use the [geemap](https://geemap.org/) Python package to visualize and analyze the Pakistan floods. Geemap enables users to analyze and visualize Earth Engine datasets interactively within a Jupyter-based environment with minimal coding. To learn more about geemap, check out https://geemap.org.

To install the required libraries, run the following command:
```bash
pip install -r requirements.txt

## Configuration File (`config.ini`)

The `config.ini` file is used to define parameters for the flood analysis. It includes the dates for "before" and "after" events, paths to datasets, and output configurations. This file ensures flexibility and reduces hardcoding in the analysis.

### Example Configuration

```ini
[GENERAL]
before_event_start = 2018-10-05       # Start date of the "before event" period
before_event_end = 2018-10-26         # End date of the "before event" period
after_event_start = 2018-10-27        # Start date of the "after event" period
after_event_end = 2018-11-20          # End date of the "after event" period
difference_threshold = 1.25           # Threshold for flood detection (e.g., NDWI/Sentinel-1)

[INPUT]
aoi_path = /path/to/aoi_shapefile.shp   # Path to Area of Interest (AOI) shapefile
s1_collection = COPERNICUS/S1_GRD       # Sentinel-1 ImageCollection ID
s2_collection = COPERNICUS/S2_SR        # Sentinel-2 ImageCollection ID
swater_dataset = JRC/GSW1_0/GlobalSurfaceWater  # Permanent water dataset (optional)

[OUTPUT]
output_directory = /path/to/output        # Directory to save raster and vector outputs
google_drive_folder = Flood_Analysis      # Google Drive folder to save exported files

