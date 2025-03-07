import streamlit as st
from streamlit_option_menu import option_menu

import digitalhub as dh 

import datetime

import flood_analysis as fa
import geemap.foliumap as geemap

st.set_page_config(
    page_title="Overturismo", layout="wide", initial_sidebar_state="expanded"
)

@st.cache_resource
def init_gee(project_name):
    
    project = dh.get_or_create_project(project_name)
    service_account = project.get_secret("service_account").read_secret_value()
    private_key_json = project.get_secret("private_key_json").read_secret_value()
    ge_project = 'dh-platform-rsde'
    fa.init_gee(ge_project, service_account, private_key_json)

PROJECT_NAME = "remote-sensing"
init_gee(PROJECT_NAME)

with st.sidebar:
    selected = option_menu(
        menu_title="Protezione Civile",
        options=["Allagamenti"],
        icons=["house"],
        menu_icon="cast",
        default_index=0,
    )

areas = [
    { "name": "Alto Garda", "date": "2020-10-03" },
    { "name": "Val di Fiemme e Val di Non", "date": "2018-10-28"},
    { "name": "Val di Fassa e Val di Non", "date": "2018-07-03"}
]
aoi_coordinates_str = '10.42,46.29; 11.62,46.29; 11.62,45.73; 10.42,45.73'


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
# c1,c2 = st.columns([1,1])
# with c1:
#     before_event_start = st.date_input("Inizio periodo prima dell'evento", '2018-10-05')
#     before_event_end = st.date_input("Fine periodo prima dell'evento", '2018-10-26')

# with c2:
#     after_event_start = st.date_input("Inizio periodo dopo l'evento", '2018-10-27')
#     after_event_end = st.date_input("Fine periodo dopo l'evento", '2018-11-20')


with st.spinner("Esecuzione in corso...", show_time=True):
    res1 = fa.flood_analysis(
        str(before_event_start), str(before_event_end), str(after_event_start), str(after_event_end), aoi_coordinates_str, 's1')
    res2 = fa.flood_analysis(
        str(before_event_start), str(before_event_end), str(after_event_start), str(after_event_end), aoi_coordinates_str, 's2')

    # Create a map and add Sentinel-1 layers
    Map_S1 = geemap.Map(center=[46.0, 11.0], zoom=10)  # Adjust center and zoom level as needed
    
    # Add before and after flood Sentinel-1 layers
    Map_S1.addLayer(res1.before, {'min': -25, 'max': 0}, 'S1 - Before Flood')
    Map_S1.addLayer(res1.after, {'min': -25, 'max': 0}, 'S1 - After Flood')
    
    # Add Sentinel-1 flood extent layer
    Map_S1.addLayer(res1.diff, {'palette': 'red'}, 'S1 - Flood Extent')
    
    # Add AOI
    # Map_S1.addLayer(res1.aoi, {}, 'AOI')
    
    # Display the map
    Map_S1.addLayerControl()  # Add layer control to toggle layers on/off
    Map_S1.to_streamlit(height=600)

