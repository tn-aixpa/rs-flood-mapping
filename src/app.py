import streamlit as st
from streamlit_option_menu import option_menu

import digitalhub as dh 

import datetime

import geopandas as gpd

import flood_analysis as fa
import geemap.foliumap as geemap

import plotly.express as px

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
        options=["Allagamenti"],
        icons=["house"],
        menu_icon="cast",
        default_index=0,
    )

areas = [
    { "name": "Alto Garda", "date": "2020-10-03", "shape": "Alto-Garda.shp" },
    { "name": " Val di Non", "date": "2018-10-28" , "shape": "Val-di-NON.shp"},
    { "name": "Val di Fassa", "date": "2018-07-03" , "shape": "Val-di-Fassa.shp"}
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
        
        Map_Flood.add_gdf(area, "AOI")
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
        
