# RS-FLOOD-MAPPING

This project implements a pipeline for flood analysis using Sentinel imagery. It processes raw .SAFE or .zip Sentinel inputs, extracts NDWI indices, detect water bodies before and after a flood event, and outputs change detection and probability maps.

#### AIxPA

- `kind`: product-template
- `ai`: remote sensing
- `domain`: PA

The context in which this project was developed: This project focuses on leveraging satellite imagery to detect flooded areas. The project pipeline downloads the indices of area of interest (Trentino) from the sentinel download tool. The software process each downloaded tile separately, clip them using python procedure to convert the downloaded data to input files and then process the clipped tiles for the deforestation.

The product contains operations for

- Download Sentinel-1 and Sentinel-2 data using tile-specific metadata
- Perform elaboration
  - Compute NDWI indices to detect water bodies before and after a flood event.
  - Calculate flood extent by analyzing pre- and post-event backscatter differences on sentine-1 data.
  - ComputeRainfall analysis(CHIRPS) to understand rainfall trend and impact on flood event.
  - Post-process change maps to improve water body masking.
- Log results as GeoTIFF raster files Raster and vector outputs.

## Prerequisites Notes!

The pipelines takes around 1-2 hours to complete with 16 CPUs and 64GB Ram for processing data window around flood event date (±20 days sentinel-2 data and ± 7days Sentinel1 data)which is the default period. It consists of interpolation and post processing steps which are computationally heavy since it is pixel based analysis. The amount of sentinal data is huge that is whay a volume of 100Gi of type 'persistent_volume_claim' is specified to ensure significant data space.

## Usage

Tool usage documentation [here](./docs/usage.md).

## How To

- [Download and preprocess sentinel flood data](./docs/howto/download.md)
- [Run Flood Elaboration and log output ](./docs/howto/elaborate.md)

## License

[Apache License 2.0](./LICENSE)
