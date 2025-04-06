import streamlit as st
from streamlit_option_menu import option_menu

import digitalhub as dh 

import datetime

import geopandas as gpd

import flood_analysis as fa

import geemap.foliumap as geemap
import geemap.colormaps as cm

import rasterio
import os
import numpy as np

import plotly.express as px
from rasterio.plot import show
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import contextily as cx

st.set_page_config(
    page_title="Protezione Civile", layout="wide", initial_sidebar_state="expanded"
)

@st.cache_resource
def init_gee(project_name):
    
    project = dh.get_or_create_project(project_name)
    service_account = project.get_secret("service_account").read_secret_value()
    private_key_json = project.get_secret("private_key_json").read_secret_value()
    ge_project = 'dh-platform-rsde'
    fa.init_gee(ge_project, service_account, private_key_json)
    try:
        project.get_artifact('areas').download('./shapes')
    except Exception as e:
        print(e)
    try:
        project.get_artifact("stacked_masked_ew_displ_map").download("./geologico")
        os.replace("./geologico/s3:/datalake/dgpv/stacked_masked_ew_displ_map.tif", "./geologico/stacked_masked_ew_displ_map.tif")
        project.get_artifact("stacked_coh_map").download("./geologico")
        os.replace("./geologico/s3:/datalake/dgpv/stacked_coh_map.tif", "./geologico/stacked_coh_map.tif")
    except Exception as e:
        print(e)



PROJECT_NAME = "remote-sensing"
init_gee(PROJECT_NAME)

# Function to plot histogram
def plot_histogram(data, title='Histogram', color='blue'):
    """Plot histogram from the Earth Engine histogram data."""
    bucket_limits = data['bucketMeans']
    counts = data['histogram']
    width = bucket_limits[1] - bucket_limits[0]
    fig = px.bar(data, y='histogram', x='bucketMeans', labels={'histogram':'Frequency', 'bucketMeans': 'NDWI'}, title=title, color_discrete_sequence=[color])
    st.plotly_chart(fig, key=title)
    
    # plt.bar(bucket_limits, counts, width=width, color=color, alpha=0.7)
    # plt.title(title)
    # plt.xlabel('NDWI')
    # plt.ylabel('Frequency')
    # plt.grid(True)
    

with st.sidebar:
    selected = option_menu(
        menu_title="Protezione Civile",
        options=[
            "Allagamenti",
            "Geologico",
        ],
        icons=["house"],
        menu_icon="cast",
        default_index=0,
    )

if selected == "Geologico":
    st.title("Analisi Geologico")

    src = rasterio.open("./geologico/stacked_masked_ew_displ_map.tif")
    coh_map_src = rasterio.open('./geologico/stacked_coh_map.tif')

    if True: #'geological' not in st.session_state:    
        crs = str(src.crs)
        transform = list(src.transform)[:6]
        ew_displ_map = np.array(src.read([1]))
        ew_displ_map[np.isnan(ew_displ_map)] = -1000
        ew_displ = geemap.numpy_to_ee(ew_displ_map,crs=crs,transform=transform)
        ew_displ_masked = ew_displ.updateMask(ew_displ.eq(-1000))
        st.session_state['geological'] = {'ew_displ_masked': ew_displ_masked}
    else: 
        ew_displ_masked = st.session_state['geological']['ew_displ_masked']
    
    palette = cm.palettes.jet
    
    # Create a map and add Sentinel-1 layers
    Map = geemap.Map(center=[46.15, 11.72], zoom=12)  # Adjust center and zoom level as needed
    
    vis_params = {'min': -0.6, 'max': 0.6, 'palette':palette}
    # Add before and after flood Sentinel-1 layers
    Map.addLayer(ew_displ_masked, vis_params, 'Mappa di scostamento est-ovest')
    #Map.addLayer(coh, {'min': 0, 'max': 1}, 'Mappa di coerenza')
    
    Map.add_colorbar(vis_params, label="Scostamento East-Ovest (m)", layer_name="legenda", font_size=9)
    # Display the map
    Map.addLayerControl()  # Add layer control to toggle layers on/off
    Map.to_streamlit(height=600)    

    fig, ax = plt.subplots(1,2,figsize=(20, 10))
    
    show(src, ax=ax[0])
    ax[0].axis('off')
    cx.add_basemap(ax[0], crs=str(src.crs))
    show(src, ax=ax[0], title='Mappa di scostamento Est-Ovest Canal San Bovo')
    # Create a legend for the blue line
    line1 = mpatches.Patch(color='#30123b', label='>5cm Ovest')
    line2 = mpatches.Patch(color='#4455c4', label='4-5cm Ovest')
    line3 = mpatches.Patch(color='#4390fe', label='3-4cm Ovest')
    line4 = mpatches.Patch(color='#1fc9dd', label='2-3cm Ovest')
    line5 = mpatches.Patch(color='#2aefa1', label='1-2cm Ovest')
    line6 = mpatches.Patch(color='#7eff55', label='0-1cm Ovest')
    line7 = mpatches.Patch(color='#c2f234', label='0-1cm Est')
    line8 = mpatches.Patch(color='#f2c93a', label='1-2cm Est')
    line9 = mpatches.Patch(color='#fe8f29', label='2-3cm Est')
    line10 = mpatches.Patch(color='#e94d0d', label='3-4cm Est')
    line11 = mpatches.Patch(color='#bd2002', label='4-5cm Est')
    line12 = mpatches.Patch(color='#7a0403', label='>5cm Est')
    legend = ax[0].legend(handles=[line1,line2,line3,line4,line5,line6,line7,line8,line9,line10,line11,line12], loc='lower right') 
    
    show(coh_map_src.read([1]), ax=ax[1], title='Mappa di coerenza Canal San Bovo',cmap='Grays_r')
    ax[1].axis('off')
    
    st.pyplot(fig)


if selected == "Allagamenti":
    
    areas = [
        { "name": "Alto Garda", "date": "2020-10-03", "shape": "Alto-Garda.shp" },
        { "name": " Val di Non", "date": "2018-10-28" , "shape": "Val-di-NON.shp"},
        { "name": "Val di Fiemme", "date": "2018-07-03" , "shape": "Val-di-Fassa.shp"}
    ]
    if 'areas' not in st.session_state:
        st.session_state['areas'] = {}
    
    # aoi_coordinates_str = '10.42,46.29; 11.62,46.29; 11.62,45.73; 10.42,45.73'
    aoi_coordinates_str = '10.20, 46.50; 11.80, 46.50; 11.80, 45.50; 10.20, 45.50'
    
    
    st.title("Analisi Allagamenti")
    
    option = st.selectbox(
        "Seleziona Area",
        areas,
        format_func=lambda x: f"{x['name']} - {x['date']}"
    )
    date = datetime.datetime.strptime(option['date'], "%Y-%m-%d")
    before_event_start = (date - datetime.timedelta(days=30)).date()
    before_event_end = (date - datetime.timedelta(days=3)).date()
    after_event_start = (date + datetime.timedelta(days=3)).date()
    after_event_end = (date + datetime.timedelta(days=30)).date()
    area = gpd.read_file(f'./shapes/{option["shape"]}').to_crs(epsg=4326)
    coords = [tuple(x) for x in area.get_coordinates().to_numpy()]
    
    Map_Flood = geemap.Map(center=[46.0, 11.0], zoom=8)
    
    with st.spinner("Esecuzione in corso...", show_time=True):
    
        # Map with Flood analysis layers
        if option['name'] not in st.session_state['areas']:    
            data = fa.flood_analysis(
                str(before_event_start), str(before_event_end), str(after_event_start), str(after_event_end), aoi_coordinates_str)
    
            # Calculate histograms
            aoi = fa.read_aoi(aoi_coordinates_str)
            try:
                hist_before = fa.get_histogram(data[5], aoi)
                hist_after = fa.get_histogram(data[6], aoi)
            except:
                hist_before = None
                hist_after = None
                
            # ✅ Add Sentinel-1 before and after layers (initially turned off)
            Map_Flood.addLayer(data[0], {'min': -25, 'max': 0}, 'S1 - Before Flood', shown=False)
            Map_Flood.addLayer(data[1], {'min': -25, 'max': 0}, 'S1 - After Flood', shown=False)
            
            # ✅ Add Sentinel-2 RGB Layers (initially turned off)
            Map_Flood.addLayer(data[2], {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000},
                               'S2 - Before Flood (RGB)', shown=False)
            Map_Flood.addLayer(data[3], {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000},
                               'S2 - After Flood (RGB)', shown=False)
            
            # ✅ Add Merged Flood Layer (initially turned off)
            Map_Flood.addLayer(data[4], {}, 'Flood Extent (S1 + S2)', shown=True)
            
            Map_Flood.add_gdf(area, "AOI", info_mode=None)
            # Display the map
            Map_Flood.addLayerControl()  # Add layer control to toggle layers on/off
    
            st.session_state['areas'][option['name']] = (Map_Flood,hist_before,hist_after)
        else:
            Map_Flood,hist_before,hist_after = st.session_state['areas'][option['name']]
    
        # from ipyleaflet import WidgetControl
        # import ipywidgets as widgets
        # # ✅ Create Custom Legend Using ipywidgets (Blue for Flood Extent)
        # legend_html = widgets.HTML(
        #     value=f"""
        #     <div style="background-color: white; padding: 10px; border: 2px solid black;">
        #         <h4>Legend</h4>
        #         <div style="display: flex; align-items: center;">
        #             <div style="width: 15px; height: 15px; background-color: blue; margin-right: 5px;"></div>Flood Extent
        #         </div>
        #         <div style="margin-top: 10px;"><strong>Total Inundated Area:</strong> 100 sq km</div>
        #     </div>
        #     """
        # )
        
        # # ✅ Add Legend to Map
        # legend_control = WidgetControl(widget=legend_html, position="bottomright")
        # Map_Flood.add_widget(legend_control)
        
        Map_Flood.to_streamlit(height=600)
    
        if hist_before and hist_after:
            c1,c2 = st.columns(2)    
            with c1:
                plot_histogram(hist_before, 'Pre-Flood NDWI Histogram', 'blue')
            with c2:
                plot_histogram(hist_after, 'Post-Flood NDWI Histogram', 'red')
        
