#!/bin/bash
ls -la /shared
cd ~
pwd
source .bashrc
export PATH="/home/nonroot/miniforge3/snap/bin:$PATH"
export PROJ_LIB=/home/nonroot/miniforge3/share/proj
export GDAL_DATA=/home/nonroot/miniforge3/share/gdal
export GDAL_DRIVER_PATH=/home/nonroot/miniforge3/lib/gdalplugins
export PROJ_DATA=/home/nonroot/miniforge3/share/proj
gdal-config --version
python --version
echo "GDAL DATA AFTER EXPORT:"
echo $GDAL_DATA
echo "PROJ_LIB AFTER EXPORT"
echo $PROJ_LIB
echo "Running flood mapping script with parameters:"
echo "{'s1PreFlood': '$1', 's1PostFlood':'$2', 's2PreFlood':'$3','s2PostFlood':'$4','geomWKT':'$5','slopeArtifact':'$6','slopeFileName':'$7','lakeShapeArtifactName':'$8','lakeShapeFileName':'$9','riverShapeArtifactName':'${10}','riverShapeFileName':'${11}','output':'${12}','eventDate':'${13}','targetCRS':'${14}','polarization':${15},'dem_threshold':${16},'slope_threshold':${17},'noise_min_pixels':${18},'river_buffer_meters':${19}}"
cd /app
python main.py "{'s1PreFlood':'$1', 's1PostFlood':'$2', 's2PreFlood':'$3','s2PostFlood':'$4','geomWKT':'$5','slopeArtifact':'$6','slopeFileName':'$7','lakeShapeArtifactName':'$8','lakeShapeFileName':'$9','riverShapeArtifactName':'${10}','riverShapeFileName':'${11}','output':'${12}','eventDate':'${13}','targetCRS':'${14}','polarization':${15},'dem_threshold':${16},'slope_threshold':${17},'noise_min_pixels':${18},'river_buffer_meters':${19}}"
exit