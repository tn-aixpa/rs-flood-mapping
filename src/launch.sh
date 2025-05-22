#!/bin/bash
ls -la /shared
cd ~
pwd
source .bashrc
echo "Flood mapping scenario"
gdal-config --version
python --version
#printenv
cd /app
python main.py "{'input1':'$1', 'input2':'$2','input3':'$3'}"
exit