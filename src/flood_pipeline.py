
from digitalhub_runtime_kfp.dsl import pipeline_context
import datetime

def myhandler(geometry, outputName, floodDate, aoiName, s1_preFloodDate, s1_postFloodDate, s2_preFloodDate, s2_postFloodDate):
  
    s1_artifact_pre = "sentinel1_GRD_preflood_" + str(outputName)
    s1_artifact_post = "sentinel1_GRD_postflood_"+ str(outputName) 
    s2_artifact_pre = "sentinel2_pre_flood_"+ str(outputName)
    s2_artifact_post =  "sentinel2_post_flood_"+ str(outputName)
    
    string_dict_data_s1Pre =  """{"satelliteParams": {"satelliteType": "Sentinel1","processingLevel": "LEVEL1","sensorMode": "IW","productType": "GRD"},"startDate":\"""" + str(s1_preFloodDate) + """\","endDate": \"""" + str(floodDate) + """\","geometry": \"""" + str(geometry) + """\","area_sampling": "True","tmp_path_same_folder_dwl":"True","artifact_name":  \"""" + str(s1_artifact_pre) + """\"}"""
    string_dict_data_s1Post = """{"satelliteParams": {"satelliteType": "Sentinel1","processingLevel": "LEVEL1","sensorMode": "IW","productType": "GRD"},"startDate":\"""" + str(floodDate) + """\","endDate": \"""" + str(s1_postFloodDate) + """\","geometry": \"""" + str(geometry) + """\","area_sampling": "True","tmp_path_same_folder_dwl":"True","artifact_name": \"""" + str(s1_artifact_post) + """\"}"""
    string_dict_data_s2Pre =  """{"satelliteParams":{"satelliteType": "Sentinel2","processingLevel": "S2MSI2A","bandmath": ["NDWI"]},"startDate":\"""" + str(s2_preFloodDate) + """\","endDate": \"""" + str(floodDate) + """\","geometry": \"""" + str(geometry) + """\","cloudCover": "[0,20]","area_sampling": "True","artifact_name" : \"""" + str(s2_artifact_pre) + """\","preprocess_data_only": "false"}"""
    string_dict_data_s2Post = """{"satelliteParams":{"satelliteType": "Sentinel2","processingLevel": "S2MSI2A","bandmath": ["NDWI"]},"startDate":\"""" + str(floodDate) + """\","endDate": \"""" + str(s2_postFloodDate) + """\","geometry": \"""" + str(geometry) + """\","cloudCover": "[0,20]","area_sampling": "True","artifact_name": \"""" + str(s2_artifact_post) + """\","preprocess_data_only": "false"}"""

    
    
    with pipeline_context() as pc:

        s1 = pc.step(name="downloadS1Pre",
                     function="download_images_s1",
                     action="job",
                     secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                     fs_group='8877',
                     args=["main.py", string_dict_data_s1Pre],
                     resources={"cpu": {"requests": "3", "limits": "6"},"mem":{"requests": "32Gi", "limits": "64Gi"}},
                     envs=[{"name": "TMPDIR", "value": "/app/files"}],
                     volumes=[{
                        "volume_type": "persistent_volume_claim",
                        "name": "volume-flood",
                        "mount_path": "/app/files",
                        "spec": { "size": "100Gi" }
                        }
                    ])

        s2 = pc.step(name="downloadS1Post",
                     function="download_images_s1",
                     action="job",
                     secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                     fs_group='8877',
                     args=["main.py", string_dict_data_s1Post],
                     resources={"cpu": {"requests": "3", "limits": "6"},"mem":{"requests": "32Gi", "limits": "64Gi"}},
                     envs=[{"name": "TMPDIR", "value": "/app/files"}],
                     volumes=[{
                        "volume_type": "persistent_volume_claim",
                        "name": "volume-flood",
                        "mount_path": "/app/files",
                        "spec": { "size": "100Gi" }
                        }
                    ]).after(s1)
        
        s3 = pc.step(name="downloadS2Pre",
                     function="download_images_s2",
                     action="job",
                     secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                     fs_group='8877',
                     args=["main.py", string_dict_data_s2Pre],
                     resources={"cpu": {"requests": "3", "limits": "6"},"mem":{"requests": "32Gi", "limits": "64Gi"}},
                     envs=[{"name": "TMPDIR", "value": "/app/files"}],
                     volumes=[{
                        "volume_type": "persistent_volume_claim",
                        "name": "volume-flood",
                        "mount_path": "/app/files",
                        "spec": { "size": "100Gi" }
                        }
                    ]).after(s2)

        s4 = pc.step(name="downloadS2Post",
                     function="download_images_s2",
                     action="job",
                     secrets=["CDSETOOL_ESA_USER","CDSETOOL_ESA_PASSWORD"],
                     fs_group='8877',
                     args=["main.py", string_dict_data_s2Post],
                     resources={"cpu": {"requests": "3", "limits": "6"},"mem":{"requests": "32Gi", "limits": "64Gi"}},
                     envs=[{"name": "TMPDIR", "value": "/app/files"}],
                     volumes=[{
                        "volume_type": "persistent_volume_claim",
                        "name": "volume-flood",
                        "mount_path": "/app/files",
                        "spec": { "size": "100Gi" }
                        }
                    ]).after(s3)

        s5 = pc.step(name="elaborate",
                     function="elaborate",
                     action="job",
                     fs_group='8877',
                     resources={"cpu": {"requests": "3", "limits": "6"},"mem":{"requests": "32Gi", "limits": "64Gi"}},
                     volumes=[{
                        "volume_type": "persistent_volume_claim",
                        "name": "volume-flood",
                        "mount_path": "/app/data",
                        "spec": { "size": "200Gi" }
                    }],
                     args=['/shared/launch.sh', str(s1_artifact_pre), str(s1_artifact_post), str(s2_artifact_pre), str(s2_artifact_post), str(geometry), 'Slopes_TN', 'trentino_slope_map.tif', 'Lakes_TN', 'idrspacq.shp', 'Rivers_TN', 'cif_pta2022_v.shp', str(outputName), str(floodDate), 'EPSG:25832', "['VV','VH']", '600', '7', '7', '1', str(aoiName)]
                     ).after(s4)
     
