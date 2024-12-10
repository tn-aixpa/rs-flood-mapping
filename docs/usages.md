## Usage

This project provides a streamlined approach to detect floods using Sentinel-1 and Sentinel-2 data, as well as rainfall analysis using CHIRPS data. Below are the steps to use the project:

### Step 1: Set Up the Environment
- Clone the repository:  
  ```sh
  git clone https://github.com/your-username/Flood-Mapping-Case.git
  ```
   ```sh
  cd Flood-Mapping-Case
  
## Requirements

To follow this project, you must:

1. [Sign up for Google Earth Engine](https://code.earthengine.google.com/register).
2. Authenticate the Earth Engine Python API by following the [instructions here](https://book.geemap.org/chapters/01_introduction.html#earth-engine-authentication).

Install the required Python libraries using the following command:

```sh
pip install -r requirements.txt
```
### Step 2: Configure the Project
Edit the config.ini file located in the repository to set the analysis parameters:
- Dates for "before" and "after" events.
- Paths to the input datasets (e.g., AOI shapefile).
- Output directory for saving results.

 ### Step 3: Run the Jupyter Notebook
Open the notebook located in the [`src`](src/) folder. Click the link to view and download the notebook.
```sh
jupyter notebook src/flood_detection_notebook.ipynb
```
- Run the notebook cells sequentially.
- Authenticate with Google Earth Engine.
- Analyze Sentinel-1 and Sentinel-2 data for flood detection.
- Perform rainfall analysis using CHIRPS data.
 ### Step 4: Access the Results

- Exported Files: The results (raster and vector outputs) will be saved in the directory specified in the config.ini file.
- Use geospatial tools such as QGIS or ArcGIS for further visualization and analysis of the outputs.
