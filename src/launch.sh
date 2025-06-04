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
echo "{'s1PreFlood', '$1', 's1PostFlood':'$2', 's2PreFlood':'$3','s2Post Flood':'$4','geomWKT':'$5','slopeArtifact':'$6','slopeFileName':'$7','lakeShapeArtifactName':'$8','lakeShapeFileName':'$9','riverShapeArtifactName':'$10','riverShapeFileName':'$11','output':'${12}','eventDate':'${13}','targetCRS':'${14}','polarization':'${15}','dem_threshold':${16},'slope_threshold':${17},'noise_min_pixels':${18},'river_buffer_meters':${19}}"
cd /app
python main.py "{'s1PreFlood': '$1', 's1PostFlood':'$2', 's2PreFlood':'$3','s2Post Flood':'$4','geomWKT':'$5','slopeArtifact':'$6','slopeFileName':'$7','lakeShapeArtifactName':'$8','lakeShapeFileName':'$9','riverShapeArtifactName':'$10','riverShapeFileName':'$11','output':'${12}','eventDate':'${13}','targetCRS':'${14}','polarization':'${15}','dem_threshold':${16},'slope_threshold':${17},'noise_min_pixels':${18},'river_buffer_meters':${19}}"
exit