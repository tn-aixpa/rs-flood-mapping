# Elaboration

## 1. Register the `elaborate` operation in the project

```python
function_rs = proj.new_function(
    "elaborate",
    kind="container",
    image="ghcr.io/tn-aixpa/rs-flood-mapping:2.6.0_b8",
    code_src="launch.sh")
```

The function represent a container runtime that allows you to deploy deployments, jobs and services on Kubernetes. It uses the base image of rs-flood-mapping container deploved in the context of project that creates the runtime environment required for the execution. It invovles pulling the base image with gdal installed and installing all the required libraries and launch instructions specified by 'launch.sh' file.

## 2. Run

The function aims at downloading all the flood inputs from project context and perform the complex task of flood analysis.

```python
run_el = function_rs.run(action="job",
            fs_group='8877',
            volumes=[{
            "volume_type": "persistent_volume_claim",
            "name": "volume-flood", # this name has to be equal to the name of the volume created in krm
            "mount_path": "/app/files",
            "spec": {
                "size": "125Gi"
            }}],
            args=['/shared/launch.sh', 'sentinel1_GRD_preflood', 'sentinel1_GRD_postflood', 'sentinel2_pre_flood', 'sentinel2_post_flood', 'POLYGON ((10.644988646837982 45.85539621678084, 10.644988646837982 46.06780100571985, 10.991744628283294 46.06780100571985, 10.991744628283294 45.85539621678084, 10.644988646837982 45.85539621678084))', 'Slopes_TN', 'slope_map25832.tif', 'Lakes_TN', 'idrspacq.shp', 'Rivers_TN', 'cif_pta2022_v.shp', 'output_flood_mask', '2020-10-02', 'EPSG:25832', ['VV','VH'], '700', '7', '15', '2']
         )
)
```

As indicated in the project documentation, the pixel based analysis performed in the elaboration steps are computation heavy. The best possible performance matrix is more or less around the configuration indicated in the step above. The amount of sentinal data can vary. A safe limit volume of 250Gi is specified as persistent volume claim to ensure significant data space. The function takes around 8-9 hours to complete with 16 CPUs and 64GB Ram for 2 years of data which is the default period. The output GeoTIFF raster file CD_2018_2019.tif along with changed map files are saved in the project context as an artifact (output_flood_mask).
