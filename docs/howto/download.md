# How to prepare data for elaboration

To prepare the deforestation data, it is required to log the data in the project context

## 1. Initialize the project

```python
import digitalhub as dh
PROJECT_NAME = "deforlood-detection" # here goes the project name that you are creating on the platform
proj = dh.get_or_create_project(PROJECT_NAME)
```

## 2. Log the Shape artifact

Log the shape file 'bosco' which can be downloaded from the [WebGIS Portal](https://webgis.provincia.tn.it/) confine del bosco layer or from https://siatservices.provincia.tn.it/idt/vector/p_TN_3d0874bc-7b9e-4c95-b885-0f7c610b08fa.zip. Unzip the files in a folder named 'bosco' and then log it

```python
artifact_name='bosco'
src_path='bosco'
artifact_bosco = proj.log_artifact(name=artifact_name, kind="artifact", source=src_path)
```

Note that to invoke the operation on the platform, the data should be avaialble as an artifact on the platform datalake.

```python
artifact = proj.get_artifact("bosco")
artifact.key
```

The resulting dataset will be registered as the project artifact in the datalake under the name `bosco`.

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

```python
string_dict_data = """{
 "satelliteParams":{
     "satelliteType": "Sentinel2"
 },
 "startDate": "2018-01-01",
 "endDate": "2019-12-31",
 "geometry": "POLYGON((10.98014831542969 45.455314263477874,11.030273437500002 45.44808893044964,10.99937438964844 45.42014226680115,10.953025817871096 45.435803739956725,10.98014831542969 45.455314263477874))",
 "area_sampling": "true",
 "cloudCover": "[0,20]",
 "artifact_name": "data_s2_deforestation"
 }"""

list_args =  ["main.py",string_dict_data]
```

Register 'download_images_s2' operation in the project. The function if of kind container runtime that allows you to deploy deployments, jobs and services on Kubernetes. It uses the base image of sentinel-tools deploved in the context of project which is a wrapper for the Sentinel download and preprocessing routine for the integration with the AIxPA platform. For more details [Click here](https://github.com/tn-aixpa/sentinel-tools/). The parameters passed for sentinel downloads includes the starts and ends dates corresponding to period of two years of data. The ouput of this step will be logged inside to the platfrom project context as indicated by parameter 'artifact_name' ('data_s2_deforestation').Several other paramters can be configures as per requirements for e.g. geometry, cloud cover percentage etc.

```python
function_s2 = proj.new_function(
    "download_images_s2",
    kind="container",
    image="ghcr.io/tn-aixpa/sentinel-tools:0.11.1_dev",
    command="python")
```

### Run the function

```python
run = function_s2.run(
    action="job",
    secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
    fs_group='8877',
    args=["main.py", string_dict_data],
    resources={"cpu": {"requests": "3", "limits": "6"},"mem":{"requests": "32Gi", "limits": "64Gi"}},
    volumes=[{
        "volume_type": "persistent_volume_claim",
        "name": "volume-deforestation",
        "mount_path": "/app/files",
        "spec": {
             "size": "350Gi"
        }
    }])
```

Check the status of function.

```python
run.refresh().status.state
```
