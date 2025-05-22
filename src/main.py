import os
from snapista import Graph, Operator, TargetBand, TargetBandDescriptors
from shapely.geometry import shape, MultiPolygon
import shapefile
import digitalhub as dh
from utils.skd_handler import upload_artifact

def shp_to_wkt(shp_path):
    r = shapefile.Reader(shp_path)
    shapes = [shape(s.__geo_interface__) for s in r.shapes()]
    merged = MultiPolygon(shapes)
    return merged.wkt

def run_pipeline_zip(zip_path, shapefile_path, output_path):
    wkt = shp_to_wkt(shapefile_path)

    g = Graph()

    g.add_node(
        Operator(
            "Read",
            file=zip_path,
            formatName="SENTINEL-1"
        ),
        node_id="read"
    )

    g.add_node(
        Operator(
            "Apply-Orbit-File",
            orbitType="Sentinel Precise (Auto Download)",
            polyDegree="3",
            continueOnFail="true"
        ),
        node_id="orbit",
        source="read"
    )

    g.add_node(
        Operator(
            "Subset",
            copyMetadata="true",
            geoRegion=wkt
        ),
        node_id="subset",
        source="orbit"
    )

    g.add_node(
        Operator(
            "Calibration",
            outputSigmaBand="true",
            outputImageScaleInDb="false",
            selectedPolarisations="VV",
            sourceBandNames="Intensity_VV"
        ),
        node_id="calibration",
        source="subset"
    )

    g.add_node(
        Operator(
            "Speckle-Filter",
            filter="Lee",
            filterSizeX="5",
            filterSizeY="5"
        ),
        node_id="speckle",
        source="calibration"
    )

    g.add_node(
    Operator(
        "Terrain-Correction",
        demName="SRTM 3Sec",
        pixelSpacingInMeter="10.0",
        mapProjection='PROJCS["ETRS89 / UTM zone 32N", GEOGCS["ETRS89", DATUM["European Terrestrial Reference System 1989", SPHEROID["GRS 1980",6378137.0, 298.257222101, AUTHORITY["EPSG","7019"]], TOWGS84[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], AUTHORITY["EPSG","6258"]], PRIMEM["Greenwich", 0.0, AUTHORITY["EPSG","8901"]], UNIT["degree", 0.017453292519943295], AXIS["Geodetic longitude", EAST], AXIS["Geodetic latitude", NORTH], AUTHORITY["EPSG","4258"]], PROJECTION["Transverse_Mercator", AUTHORITY["EPSG","9807"]], PARAMETER["central_meridian", 9.0], PARAMETER["latitude_of_origin", 0.0], PARAMETER["scale_factor", 0.9996], PARAMETER["false_easting", 500000.0], PARAMETER["false_northing", 0.0], UNIT["m", 1.0], AXIS["Easting", EAST], AXIS["Northing", NORTH], AUTHORITY["EPSG","25832"]]'
        ),
    node_id="tc",
    source="speckle"
    )

    flood_band = TargetBand(name='Sigma0_VV_Flooded',
                              expression="(Sigma0_VV < 1.13E-2) ? 1 : 0")
    g.add_node(
        Operator(
            "BandMaths",
            targetBandDescriptors=TargetBandDescriptors([flood_band])
        ),
        node_id="mask",
        source="tc"
    )

    g.add_node(
    Operator(
        "Write",
        file=output_path + ".tif",
        formatName="GeoTIFF-BigTIFF"
    ),
    node_id="write",
    source="mask"
    )
    g.run()
    print(f" Flood mask written to {output_path}.tif")




if __name__ == "__main__":
    args = sys.argv[1].replace("'","\"")
    json_input = json.loads(args)
    
    maindir = '.'
    datapath = 'data'
    outpath = 'output'
    
    
    input1 = json_input['input1']
    project_name=os.environ["PROJECT_NAME"]
    input2 = json_input['input2']
    
    print(f"input1: {input1}, input2:{input2}, project:{project_name}")
    
    output_folder = os.path.join(outpath, "flood_mask")
    project_name=os.environ["PROJECT_NAME"]
    project = dh.get_or_create_project(project_name)
    # download data
    shp_data = project.get_artifact(input1)
    shp_path =  shp_data.download(datapath, overwrite=True)
    sentinel_data = project.get_artifact(input2)
    sentinel_zip_path=os.path.join(datapath, "sentinel_zips")
    sentinel_zip_path = sentinel_data.download(sentinel_zip_path, overwrite=True) 
    run_pipeline_zip(sentinel_zip_path, shp_path, output_folder)
    print(f"Upoading artifact: {artifact_name}, {artifact_name}")
    upload_artifact(artifact_name=artifact_name,project_name=project_name,src_path=output_folder)
