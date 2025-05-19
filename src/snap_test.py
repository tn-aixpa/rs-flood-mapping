#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jan 17 11:35:17 2025

@author: lbergamasco
"""

from snapista import Operator
from snapista import Graph
import os

if __name__ == "__main__":
    input_path = "data2"
    list_files = [f for f in os.listdir(input_path) if ".zip" in f]
    file1 = os.path.join(input_path, list_files[1])
    file2 = os.path.join(input_path, list_files[0])
    
    print("Reading:\n{}\n{}".format(file1,file2))
    g = Graph()
    g.add_node(Operator("Read",formatName="SENTINEL-1",file=file1), node_id="read1")
    g.add_node(Operator("Read",formatName="SENTINEL-1",file=file2), node_id="read2")
    
    #TOPS Split
    print("Coregistration...")
    tops_split = Operator("TOPSAR-Split")
    tops_split.subswath = "IW1"
    tops_split.selectedPolarisations = "VV"
    tops_split.firstBurstIndex = 1
    tops_split.lastBurstIndex = 5
    g.add_node(tops_split,node_id="TOPS-SPLIT1",source="read1")
    g.add_node(tops_split, node_id="TOPS-SPLIT2",source="read2")
    
    #Apply orbit
    file1orbit = file1[:-9]+"_split_Orb"
    file2orbit = file2[:-9]+"_split_Orb"
    orbit = Operator("Apply-Orbit-File",orbitType="Sentinel Precise (Auto Download)",continueOnFail="true")
    g.add_node(orbit,node_id="orbit1",source="TOPS-SPLIT1")
    g.add_node(orbit,node_id="orbit2",source="TOPS-SPLIT2")
    g.add_node(Operator("Write", file=file1orbit+".dim"),
               node_id="writer1orbit",source="orbit1")
    g.add_node(Operator("Write", file=file2orbit+".dim"),
               node_id="writer2orbit",source="orbit2")
