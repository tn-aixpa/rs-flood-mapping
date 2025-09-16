# RS-FLOOD-MAPPING

<p align="justify">This project implements a pipeline for flood analysis using Sentinel imagery. It processes raw .SAFE or .zip Sentinel inputs, extracts NDWI indices, detect water bodies before and after a flood event, and outputs change detection and probability maps.</p>

#### AIxPA

- `kind`: product-template
- `ai`: remote sensing
- `domain`: PA

<p align="justify">The context in which this project was developed: This project focuses on leveraging satellite imagery to detect flooded areas. The project pipeline downloads the indices of area of interest (Trentino) from the sentinel download tool. The software process each downloaded tile separately, clip them using python procedure to convert the downloaded data to input files and then process the clipped tiles for the flood analysis.</p>

The product contains operations for

- Download Sentinel-1 and Sentinel-2 data using tile-specific metadata
- Perform elaboration
  - Compute NDWI indices to detect water bodies before and after a flood event.
  - Calculate flood extent by analyzing pre- and post-event backscatter differences on sentine-1 data.
  - ComputeRainfall analysis(CHIRPS) to understand rainfall trend and impact on flood event.
  - Post-process change maps to improve water body masking.
- Log results as GeoTIFF raster files Raster and vector outputs.

## Requirements!

### Hardware Requirements

<p align="justify">The pipelines can take several hours to complete with 16 CPUs and 64GB Ram for processing data window around flood event date (±20 days sentinel-2 data and ± 7days Sentinel1 data)which is the default period. It consists of two steps (download, elaboration). The download step is dependant on Sentinel Hub dataspace. It could happen that data download takes more time than usual due to various factors, including technical issues, data processing delays, and limitations in the data access infrastructure. The second step 'elaboration' consists of interpolation and post processing steps which are computationally heavy since it is pixel based analysis. The amount of sentinal data is huge that is whay a volume of 100Gi of type 'persistent_volume_claim' is specified to ensure significant data space.</p>

### General Requirements.

- Register to the open data space copenicus(if not already) and get your credentials.

```
https://identity.dataspace.copernicus.eu/auth/realms/CDSE/login-actions/registration?client_id=cdse-public&tab_id=FIiRPJeoiX4
```

- Download Lakes shape data from from portal <siat.provincia.tn.it> catalog by searching for term 'Laghi e specchi d'acqua' or download directly here

```
https://siat.provincia.tn.it/geonetwork/srv/ita/catalog.search#/metadata/p_TN:0f1fdc33-5c71-4c6d-81e7-25eb2ab0e599
```

- Download Rivers shape data from from portal <siat.provincia.tn.it> catalog by searching for term 'PTA River Water Bodies 2022' or download directly here

```
https://siat.provincia.tn.it/geonetwork/srv/ita/catalog.search#/metadata/p_TN:df06e63c-d0f3-46c9-8ec2-c25a22c50ef7
```

-  Download the Slope data from direct link on the <a href="https://huggingface.co/datasets/lbergamasco/trentino-slope-map/blob/main/trentino_slope_map.tif">Huggingface repository</a>

## Usage

Tool usage documentation [here](./docs/usage.md).

## How To

- [Download and preprocess sentinel flood data](./docs/howto/download.md)
- [Run Flood Elaboration and log output ](./docs/howto/elaborate.md)
- [Workflow](./docs/howto/workflow.md)

## License

[Apache License 2.0](./LICENSE)
