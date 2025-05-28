#!/bin/bash
ls -la /shared
cd ~
pwd
source .bashrc
echo "Flood mapping scenario"
gdal-config --version
python --version
export PATH="/home/nonroot/miniforge3/snap/bin:$PATH"
export PATH="/home/nonroot/miniforge3/snap/.snap/auxdata/gdal/gdal-3-0-0/bin/:$PATH"
cd /app
python main.py "{'input1':'$1', 'input2':'$2','input3':'$3','input4':'$4','input5':'$5','input6':'$6','input7':'$7','input8':'$8','input9':'$9','input10':'${10}','input11':'${11}','input12':'${12}','input13':'${13}','input14':${14},'input15':${15},'input16':${16},'input17':${17}}"
exit