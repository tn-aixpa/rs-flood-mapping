# Workflow

<p align="justify">In this step we will create a workflow pipeline that establish a clear, repeatable process for handling the set of scenario tasks (download, elaborate). The DH platform pipeline ensures that tasks are completed in a sepcific order. It also provide the ease to fine tune the steps as per requirements of scenario imporving efficiency, consistency, aand traceability. For more detailed information about workflow and their management see the <a href="https://scc-digitalhub.github.io/docs/tasks/workflows">documentation</a>. Inside the project 'src' folder there exist a jypter notebook <a href="../../src/workflow.ipynb">workflow.ipynb</a> that depicts the creation and management of workflow.</p>

## 1. Initialize the project

Create the working context: data management project for scenario. Project is a placeholder for the code, data, and management of the data operations and workflows. To keep it reproducible, we use the git source type to store the definition and code.

```python
import digitalhub as dh
PROJECT_NAME = "flood-detection" # here goes the project name that you are creating on the platform
proj = dh.get_or_create_project(PROJECT_NAME)
```

## 2. Log the Shape files artifact

The pipeline requires shape files input of river, lakes, and slope.

<p align="justify">Log the river shape file. Download the zip file from the <a href="https://siat.provincia.tn.it/geonetwork/srv/ita/catalog.search#/metadata/p_TN:df06e63c-d0f3-46c9-8ec2-c25a22c50ef7">SIAT Portal</a> and extract the contents inside a folder 'Rivers_TN' and log it as project artifact</p>

```python
artifact_name='Rivers_TN'
src_path='Rivers_TN'
artifact_bosco = proj.log_artifact(name=artifact_name, kind="artifact", source=src_path)
```

<p align="justify">Log the lakes shape file. Download the zip file from the <a href="https://siat.provincia.tn.it/geonetwork/srv/ita/catalog.search#/metadata/p_TN:0f1fdc33-5c71-4c6d-81e7-25eb2ab0e599">SIAT Portal</a> and extract the contents inside a folder 'Lakes_TN' and log it as project artifact</p>

```python
artifact_name='Lakes_TN'
src_path='Lakes_TN'
artifact_bosco = proj.log_artifact(name=artifact_name, kind="artifact", source=src_path)
```

<p align="justify">Log the slope shape file. Download the zip file from the <a href="https://huggingface.co/datasets/lbergamasco/trentino-slope-map/blob/main/trentino_slope_map.tif">Huggingface repository</a> and extract the contents inside a folder 'Slopes_TN' and log it as project artifact</p>

```python
artifact_name='Slopes_TN'
src_path='Slopes_TN'
artifact_bosco = proj.log_artifact(name=artifact_name, kind="artifact", source=src_path)
```

The resulting datasets will be registered as the project artifact in the datalake under the given names ('Rivers_TN', 'Slopes_TN', 'Lakes_TN').

## 3. Register 'Download' operations for sentinel1 and Sentine2 data

Register to the open data space copernicus(if not already) and get your credentials.

```
https://identity.dataspace.copernicus.eu/auth/realms/CDSE/login-actions/registration?client_id=cdse-public&tab_id=FIiRPJeoiX4
```

Log the credentials as project secret keys as shown below

```python
# THIS NEED TO BE EXECUTED JUST ONCE
secret0 = proj.new_secret(name="CDSETOOL_ESA_USER", secret_value="esa_username")
secret1 = proj.new_secret(name="CDSETOOL_ESA_PASSWORD", secret_value="esa_password")
```

<p align="justify">Register 'download_images_s2' operation in the project. The function is of kind container runtime that allows you to deploy deployments, jobs and services on Kubernetes. It uses the base image of sentinel-tools deploved in the context of project which is a wrapper for the Sentinel download and preprocessing routine for the integration with the AIxPA platform. For more details click <a href="https://github.com/tn-aixpa/sentinel-tools/">here</a>. The purpose of 'download_images_s2' function is to download sentinel-2 data (GRD image tiles)</p>

```python
function_s2 = proj.new_function(
    "download_images_s2",
    kind="container",
    image="ghcr.io/tn-aixpa/sentinel-tools:0.11.6",
    command="python")
```

Register 'download_images_s1' operation in the project.

```python
function_s1 = proj.new_function(
    "download_images_s1",
    kind="container",
    image="ghcr.io/tn-aixpa/sentinel-tools:0.11.6",
    command="python")
```

The purpose of this function is to download sentinel1 data(GRD image tiles) based on input parameters for e.g. geometry, cloud cover percentage etc.

## 4. Register the `elaborate` operation in the project

```python
function_rs = proj.new_function(
    "elaborate",
    kind="container",
    image="ghcr.io/tn-aixpa/rs-flood-mapping:3.2",
    code_src="launch.sh")
```

<p align="justify">The function represent a container runtime that allows you to deploy deployments, jobs and services on Kubernetes. It uses the base image of rs-flood-mapping container deploved in the context of project that creates the runtime environment required for the execution. It invovles pulling the base image with gdal installed and installing all the required libraries and launch instructions specified by 'launch.sh' file.</p>

## 5. Create workflow pipeline

Workflows can be created and managed as entities similar to functions. From the console UI one can access them from the dashboard or the left menu. Run the following step to create 'workflow' python source file inside src directory. The workflow handler takes as input

- geometry (area of interest)
- outputName (output artifact name)
- floodDate (flood event date)
- s1_preFloodDate (sentinel-1 data 7 days before flood event)
- s1_postFloodDate (sentinel-1 data 7 days after flood event)
- s2_preFloodDate (sentinel-2 data 20 days before flood event)
- s2_postFloodDate (sentinel-2 data 20 days after flood event)

<p align="justify">The inputs are sub organized inside to the workflow among different functions. The first four download steps perform sentinel downloads using the function created in previous step. The download function takes as input a list of arguments (args=["main.py", string_dict_data_s1Pre]) where the first argument is the python script file that will be launched inside to the container and the second argument is the json input string which includes all the necessary parameters of sentinel download operation like date, geometry, product type, cloud cover etc. For more details click <a href="https://github.com/tn-aixpa/sentinel-tools/">here</a>. The last step of workflow perform elaboration using the 'elaborate' function created in previous step. The elaboration function taks as input a list of arguments where the first argument is the bash script that will be launched on entry inside to the container while the following parameters contains both fixed and dynamic parameters. The fixed parameter includes both the project artifacts names (sentinel1_GRD_preflood, sentinel1_GRD_postflood, sentinel2_pre_flood, sentinel2_post_flood, 'Slopes_TN', 'trentino_slope_map.tif', 'Lakes_TN', 'idrspacq.shp', 'Rivers_TN', 'cif_pta2022_v.shp') as well as the the scenario configuration parameters like targetCRS, polarization, dem_threshold, slope_threshold, noise_min_pixels, river_buffer_meters. The set of dynamic parameters included outputName, floodDate, geometry etc. which can be passed as input to the main workflow. The workflow can be adopted as per context needs by changing/passing the different parametric values as depicted in 'Register workflow' section.</p>

```python
%%writefile "flood_pipeline_hera.py"

from hera.workflows import Workflow, DAG, Parameter
from digitalhub_runtime_hera.dsl import step

def pipeline():
    # Create a new Workflow with an entrypoint DAG and a parameter
    with Workflow(entrypoint="dag", arguments=[
        Parameter(name="geometry"),
        Parameter(name="outputName"),
        Parameter(name="floodDate"),
        Parameter(name="aoiName"),
        Parameter(name="s1_preFloodDate"),
        Parameter(name="s1_postFloodDate"),
        Parameter(name="s2_preFloodDate"),
        Parameter(name="s2_postFloodDate"),
        ]) as w:

        with DAG(name="dag"):
            # Create a new Workflow with an entrypoint DAG and a parameter
            s1_artifact_pre = "sentinel1_GRD_preflood_" + str(w.get_parameter("outputName"))
            s1_artifact_post = "sentinel1_GRD_postflood_"+ str(w.get_parameter("outputName"))
            s2_artifact_pre = "sentinel2_pre_flood_"+ str(w.get_parameter("outputName"))
            s2_artifact_post =  "sentinel2_post_flood_"+ str(w.get_parameter("outputName"))
                    
            string_dict_data_s1Pre =  """{"satelliteParams": {"satelliteType": "Sentinel1","processingLevel": "LEVEL1","sensorMode": "IW","productType": "GRD"},"startDate":\"""" + str(w.get_parameter("s1_preFloodDate")) + """\","endDate": \"""" + str(w.get_parameter("floodDate")) + """\","geometry": \"""" + str(w.get_parameter("geometry")) + """\","area_sampling": "True","tmp_path_same_folder_dwl":"True","artifact_name":  \"""" + str(s1_artifact_pre) + """\"}"""
            string_dict_data_s1Post = """{"satelliteParams": {"satelliteType": "Sentinel1","processingLevel": "LEVEL1","sensorMode": "IW","productType": "GRD"},"startDate":\"""" + str(w.get_parameter("floodDate")) + """\","endDate": \"""" + str(w.get_parameter("s1_postFloodDate")) + """\","geometry": \"""" + str(w.get_parameter("geometry")) + """\","area_sampling": "True","tmp_path_same_folder_dwl":"True","artifact_name": \"""" + str(s1_artifact_post) + """\"}"""
            string_dict_data_s2Pre =  """{"satelliteParams":{"satelliteType": "Sentinel2","processingLevel": "S2MSI2A","bandmath": ["NDWI"]},"startDate":\"""" + str(w.get_parameter("s2_preFloodDate")) + """\","endDate": \"""" + str(w.get_parameter("floodDate")) + """\","geometry": \"""" + str(w.get_parameter("geometry")) + """\","cloudCover": "[0,20]","area_sampling": "True","artifact_name" : \"""" + str(s2_artifact_pre) + """\","preprocess_data_only": "false"}"""
            string_dict_data_s2Post = """{"satelliteParams":{"satelliteType": "Sentinel2","processingLevel": "S2MSI2A","bandmath": ["NDWI"]},"startDate":\"""" + str(w.get_parameter("floodDate")) + """\","endDate": \"""" + str(w.get_parameter("s2_postFloodDate")) + """\","geometry": \"""" + str(w.get_parameter("geometry")) + """\","cloudCover": "[0,20]","area_sampling": "True","artifact_name": \"""" + str(s2_artifact_post) + """\","preprocess_data_only": "false"}"""

            s1 = step(template={"action":"job",
                                "args":["main.py", string_dict_data_s1Pre],
                                "secrets":["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                                "fs_group":"8877",
                                "resources":{"cpu": "6", "mem": "32Gi"},
                                "envs":[{"name": "TMPDIR", "value": "/app/files"}],
                                "volumes":[{"volume_type": "persistent_volume_claim","name": "volume-flood","mount_path": "/app/files","spec": { "size": "100Gi" }}]
                               }, 
                    function="download-images-s1",
                    name="s1-pre"
                   )
            
            s2 = step(template={"action":"job",
                                "args": ["main.py", string_dict_data_s1Post],
                                "secrets":["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                                "fs_group":"8877",
                                "resources":{"cpu": "6", "mem": "32Gi"},
                                "envs":[{"name": "TMPDIR", "value": "/app/files"}],
                                "volumes":[{"volume_type": "persistent_volume_claim","name": "volume-flood","mount_path": "/app/files","spec": { "size": "100Gi" }}]
                               },
                    function="download-images-s1",
                    name="s1-post"
                    )
            
            s3 = step(template={"action":"job",
                                "args": ["main.py", string_dict_data_s2Pre],
                                "secrets":["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                                "fs_group":"8877",
                                "resources":{"cpu": "6", "mem": "32Gi"},                                
                                "envs":[{"name": "TMPDIR", "value": "/app/files"}],
                                "volumes":[{"volume_type": "persistent_volume_claim","name": "volume-flood","mount_path": "/app/files","spec": { "size": "100Gi" }}]
                               },
                    function="download-images-s2",
                    name="s2-pre"
                    )
                    
            s4 = step(template={"action":"job",
                                "args": ["main.py", string_dict_data_s2Post],
                                "secrets":["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                                "fs_group":"8877",
                                "resources":{"cpu": "6", "mem": "32Gi"},                                
                                "envs":[{"name": "TMPDIR", "value": "/app/files"}],
                                "volumes":[{"volume_type": "persistent_volume_claim","name": "volume-flood","mount_path": "/app/files","spec": { "size": "100Gi" }}]
                               },
                    function="download-images-s2",
                    name="s2-post"
                    )
            
            s5 = step(template={"action":"job",
                                "args": ['/shared/launch.sh', str(s1_artifact_pre), str(s1_artifact_post), str(s2_artifact_pre), str(s2_artifact_post), str(w.get_parameter("geometry")), 'Slopes_TN', 'trentino_slope_map.tif', 'Lakes_TN', 'idrspacq.shp', 'Rivers_TN', 'cif_pta2022_v.shp', str(w.get_parameter("outputName")), str(w.get_parameter("floodDate")), 'EPSG:25832', "['VV','VH']", '900', '17', '9', '4', str(w.get_parameter("aoiName"))],
                                "fs_group":"8877",
                                "resources":{"cpu": "6", "mem":"32Gi"},
                                "envs":[{"name": "TMPDIR", "value": "/app/data"}],
                                "volumes":[{"volume_type": "persistent_volume_claim","name": "volume-flood","mount_path": "/app/data","spec": { "size": "200Gi" }}]
                               },
                    function="elaborate",
                    name="elaborate"
                    )
            
            s1 >> s2 >> s3 >> s4 >> s5

    return w
```

There is a committed version of this file on the repo.

## 6. Register workflow

Register workflow 'pipeline_flood' in the project. In the following step, we register the workflow using the committed version of pipeline source code on project git repository. It is required to update the 'code_src' url with github username and personal access token in the code cell below

```python
workflow = proj.new_workflow(
name="pipeline_flood",
kind="hera",
code_src="git+https://<username>:<personal_access_token>@github.com/tn-aixpa/rs-flood-detection",
handler="src.flood_pipeline:myhandler")
```

<p align="justify">If you want to modify the pipeline source code, either update the existing version on github repo or register the pipeline with locally modified version of python source file for e.g. the value of parameter 'artifact_name' is set to 'sentinel1_GRD_preflood' in first step S1 of pipeline. If you want to log the artifact with different name inside to the DH platform project, create/update the pipeline code locally by replacing the value of 'artifact_name' key followed by the registration of pipeline using the locally modified file as shown below.</p>

```python
workflow = proj.new_workflow(name="pipeline_flood", kind="hera", code_src= "flood_pipeline.py", handler = "myhandler")
```

## 7. Build workflow

```python
wfbuild = workflow.run(action="build", wait=True)
wfbuild.spec
```