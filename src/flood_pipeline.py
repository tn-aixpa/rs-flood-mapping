
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
