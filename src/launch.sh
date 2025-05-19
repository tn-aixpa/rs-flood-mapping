#!/bin/bash
ls -la /shared
cd ~
pwd
source .bashrc
echo "Flood mapping scenario"
gdal-config --version
python --version
printenv
cd /app
python main.py "{'input1':'bosco', 'input2': 'data', 'input3':['2018', '2019'], 'input4': 'flood_mask_output'}"
exit