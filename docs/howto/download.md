# How to prepare data for elaboration

To prepare the deforestation data, it is required to log the data in the project context

## 1. Initialize the project

```python
import digitalhub as dh
PROJECT_NAME = "flood-detection" # here goes the project name that you are creating on the platform
proj = dh.get_or_create_project(PROJECT_NAME)
```

## 2. Log the Shape files artifact

The pipeline requires shape files input of river, lakes, and slope.

Log the river shape file. Download the zip file from the [SIAT Portal](https://siat.provincia.tn.it/geonetwork/srv/ita/catalog.search#/metadata/p_TN:df06e63c-d0f3-46c9-8ec2-c25a22c50ef7) and extract the contents inside a folder 'Rivers_TN' and log it as project artifact

```python
artifact_name='Rivers_TN'
src_path='Rivers_TN'
artifact_bosco = proj.log_artifact(name=artifact_name, kind="artifact", source=src_path)
```

Log the lakes shape file. Download the zip file from the [SIAT Portal](https://siat.provincia.tn.it/geonetwork/srv/ita/catalog.search#/metadata/p_TN:0f1fdc33-5c71-4c6d-81e7-25eb2ab0e599) and extract the contents inside a folder 'Lakes_TN' and log it as project artifact

```python
artifact_name='Lakes_TN'
src_path='Lakes_TN'
artifact_bosco = proj.log_artifact(name=artifact_name, kind="artifact", source=src_path)
```

Log the slope shape file. Download the zip file from the [SIAT Portal](https://webgis.provincia.tn.it/) and extract the contents inside a folder 'Slopes_TN' and log it as project artifact

```python
artifact_name='Slopes_TN'
src_path='Slopes_TN'
artifact_bosco = proj.log_artifact(name=artifact_name, kind="artifact", source=src_path)
```

Note that to invoke the operation on the platform, the data should be avaialble as an artifact on the platform datalake.

```python
artifact = proj.get_artifact("Rivers_TN")
artifact.key
```

The resulting datasets will be registered as the project artifact in the datalake under the given names ('Rivers_TN', 'Slopes_TN', 'Lakes_TN').

## 3. Download Sentinel Data.

Register to the open data space copenicus(if not already) and get your credentials.

```
https://identity.dataspace.copernicus.eu/auth/realms/CDSE/login-actions/registration?client_id=cdse-public&tab_id=FIiRPJeoiX4
```

Log the credentials as project secret keys as shown below

```python
# THIS NEED TO BE EXECUTED JUST ONCE
secret0 = proj.new_secret(name="CDSETOOL_ESA_USER", secret_value="esa_username")
secret1 = proj.new_secret(name="CDSETOOL_ESA_PASSWORD", secret_value="esa_password")
```

### Post flood Sentinel2 data +20days

Register 'download_images_s2' operation in the project. The function if of kind container runtime that allows you to deploy deployments, jobs and services on Kubernetes. It uses the base image of sentinel-tools deploved in the context of project which is a wrapper for the Sentinel download and preprocessing routine for the integration with the AIxPA platform. For more details [Click here](https://github.com/tn-aixpa/sentinel-tools/). The parameters passed for sentinel downloads includes the starts and ends dates corresponding to period of two years of data. The ouput of this step will be logged inside to the platfrom project context as indicated by parameter 'artifact_name' ('data_s2_deforestation').Several other paramters can be configures as per requirements for e.g. geometry, cloud cover percentage etc.

```python
function_s2 = proj.new_function("download_images_s2",kind="container",image="ghcr.io/tn-aixpa/sentinel-tools:0.11.5",command="python")
```

```python
string_dict_data = """{
 "satelliteParams":{
    "satelliteType": "Sentinel2",
    "processingLevel": "S2MSI2A",
	"bandmath": ["NDWI"]
 },
 "startDate": "2020-10-02",
 "endDate": "2020-10-22",
 "geometry": "POLYGON ((10.644988646837982 45.85539621678084, 10.644988646837982 46.06780100571985, 10.991744628283294 46.06780100571985, 10.991744628283294 45.85539621678084, 10.644988646837982 45.85539621678084))",
 "cloudCover": "[0,20]",
 "area_sampling": "True",
 "artifact_name": "sentinel2_post_flood",
 "preprocess_data_only": "false"
 }"""

list_args =  ["main.py",string_dict_data]
```

Run the function. As a result the post flood sentinel-2 data is logged as project artifact('sentinel2_post_flood')

```python
run = function_s2.run(action="job",
        secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
        fs_group='8877',
        args=list_args,
        resources={"mem":{"requests": "32Gi", "limits": "64Gi"}},
        volumes=[{
            "volume_type": "persistent_volume_claim",
            "name": "volume-flood",
            "mount_path": "/app/files",
            "spec": {
                "size": "100Gi"
            }}])
```

### Pre flood Sentinel2 data -20 days

```python
string_dict_data = """{
     "satelliteParams":{
        "satelliteType": "Sentinel2",
        "processingLevel": "S2MSI2A",
    	"bandmath": ["NDWI"]
     },
     "startDate": "2020-09-12",
     "endDate": "2020-10-02",
     "geometry": "POLYGON ((10.644988646837982 45.85539621678084, 10.644988646837982 46.06780100571985, 10.991744628283294 46.06780100571985, 10.991744628283294 45.85539621678084, 10.644988646837982 45.85539621678084))",
     "cloudCover": "[0,20]",
     "area_sampling": "True",
     "artifact_name": "sentinel2_pre_flood",
     "preprocess_data_only": "false"
     }"""

list_args =  ["main.py",string_dict_data]
```

Run the function again. As a result the pre flood sentinel-2 data is logged as project artifact('sentinel2_post_flood')

```python
run = function_s2.run(action="job",
        secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
        fs_group='8877',
        args=list_args,
        resources={"mem":{"requests": "32Gi", "limits": "64Gi"}},
        volumes=[{
            "volume_type": "persistent_volume_claim",
            "name": "volume-flood",
            "mount_path": "/app/files",
            "spec": {
                "size": "100Gi"
            }}])
```

Check the status of function.

```python
run.refresh().status.state
```

### Post flood Sentinel1 data +7days

Register 'download_images_s1' operation in the project.

```python
function_s1 = proj.new_function("download_images_s1",kind="container",image="ghcr.io/tn-aixpa/sentinel-tools:0.11.5",command="python")
```

Run this function with input parameters as shown below. The parameters passed for sentinel-1 downloads includes the starts and ends dates corresponding to period of 7 days from flood event date. The ouput of this step will be logged inside to the platfrom project context as indicated by parameter 'artifact_name' ('sentinel1_GRD_postflood').Several other paramters can be configures as per requirements for e.g. geometry, cloud cover percentage etc.

Run the function. As a result the post flood sentinel-2 data is logged as project artifact('sentinel2_post_flood')

```python
string_dict_data = """{
  "satelliteParams": {
          "satelliteType": "Sentinel1",
          "processingLevel": "LEVEL1",
          "sensorMode": "IW",
          "productType": "GRD"
      },
      'startDate': '2020-10-02',
      'endDate': '2020-10-09',
      'geometry': 'POLYGON ((10.644988646837982 45.85539621678084, 10.644988646837982 46.06780100571985, 10.991744628283294 46.06780100571985, 10.991744628283294 45.85539621678084, 10.644988646837982 45.85539621678084))',
      'area_sampling': 'True',
      'tmp_path_same_folder_dwl':'True',
      'artifact_name': 'sentinel1_GRD_postflood'
  }"""
list_args =  ["main.py",string_dict_data]
```

```python
run = function_s1.run(action="job",
        secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
        fs_group='8877',
        args=list_args,
        volumes=[{
            "volume_type": "persistent_volume_claim",
            "name": "volume-flood",
            "mount_path": "/app/files",
            "spec": {
                "size": "100Gi"
            }}])
```

### Pre flood Sentinel1 data -7days

Similary download the sentine-1 data pre flood event.

```python
string_dict_data = """{
  "satelliteParams": {
          "satelliteType": "Sentinel1",
          "processingLevel": "LEVEL1",
          "sensorMode": "IW",
          "productType": "GRD"
      },
      'startDate': '2020-09-25',
      'endDate': '2020-10-02',
      'geometry': 'POLYGON ((10.644988646837982 45.85539621678084, 10.644988646837982 46.06780100571985, 10.991744628283294 46.06780100571985, 10.991744628283294 45.85539621678084, 10.644988646837982 45.85539621678084))',
      'area_sampling': 'True',
      'tmp_path_same_folder_dwl':'True',
      'artifact_name': 'sentinel1_GRD_preflood'
  }"""

# s3 path is not mandatory

list_args =  ["main.py",string_dict_data]
```

```python
run = function_s1.run(action="job",
        secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
        fs_group='8877',
        args=list_args,
        volumes=[{
            "volume_type": "persistent_volume_claim",
            "name": "volume-flood",
            "mount_path": "/app/files",
            "spec": {
                "size": "100Gi"
            }}])
```
