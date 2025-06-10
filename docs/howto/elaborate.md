# Elaboration

## 1. Register the `elaborate` operation in the project

```python
function_rs = proj.new_function(
    "elaborate",
    kind="container",
    image="ghcr.io/tn-aixpa/rs-deforestation:2.6_b8",
    command="/bin/bash",
    code_src="launch.sh"
    )
```

The function represent a container runtime that allows you to deploy deployments, jobs and services on Kubernetes. It uses the base image of rs-deforestation container deploved in the context of project create the environment required for the execution. It invovles pulling the base image with gdal installed and installing all the required libraries and launch instructions specified by 'launch.sh' file.

## 2. Run

The function aims at downloading all the deforestation inputs from project context and perform the complex task of deforesation elaboration.

```python
run_el = function_rs.run(
    action="job",
    fs_group='8877',
    resources={"cpu": {"requests": "6", "limits": "12"},"mem":{"requests": "32Gi", "limits": "64Gi"}},
    volumes=[{
        "volume_type": "persistent_volume_claim",
        "name": "volume-deforestation",
        "mount_path": "/app/files",
        "spec": { "size": "250Gi" }
    }],
    args=['/shared/launch.sh', 'bosco', 'data_s2_deforestation', '[2018,2019]',  'deforestation_2018_19']
)
```

As indicated in the project documentation, the pixel based analysis performed in the elaboration steps are computation heavy. The best possible performance matrix is more or less around the configuration indicated in the step above. The amount of sentinal data can vary. A safe limit volume of 250Gi is specified as persistent volume claim to ensure significant data space. The function takes around 8-9 hours to complete with 16 CPUs and 64GB Ram for 2 years of data which is the default period. The output GeoTIFF raster file CD_2018_2019.tif along with changed map files of two years are saved in the project context as an artifact (deforestation_2018_19).
