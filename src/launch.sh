#!/bin/bash
ls -la /shared
cd ~
pwd
source .bashrc
export PATH="/home/nonroot/miniforge3/snap/bin:$PATH"
export PATH="/home/nonroot/miniforge3/snap/.snap/auxdata/gdal/gdal-3-0-0/bin/:$PATH"
gdal-config --version
python --version
echo "Running flood mapping script with parameters:"
echo "{'s1PostFlood': '$1','s2PostFlood': '$2','s2PreFlood': '$3','AOIShapeArtifact': '$4','AOIShapeName': '$5','lakeShapeArtifactName': '$6','lakeShapeFileName': '$7','riverShapeArtifactName': '$8','riverShapeFileName': '$9','output': '${10}','eventDate': '${11}','targetCRS': '${12}','polarization': '${13}','dem_threshold': ${14},'slope_threshold': ${15},'noise_min_pixels': ${16},'river_buffer_meters': ${17}}"
cd /app
python main.py "{'s1PostFlood':'$1', 's2PostFlood':'$2','s2PreFlood':'$3','AOIShapeArtifact':'$4','AOIShapeName':'$5','lakeShapeArtifactName':'$6','lakeShapeFileName':'$7','riverShapeArtifactName':'$8','riverShapeFileName':'$9','output':'${10}','eventDate':'${11}','targetCRS':'${12}','polarization':'${13}','dem_threshold':${14},'slope_threshold':${15},'noise_min_pixels':${16},'river_buffer_meters':${17}}"
exit