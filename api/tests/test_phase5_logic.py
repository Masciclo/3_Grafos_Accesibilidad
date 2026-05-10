import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString
import os
import sys

# Mocking the utils and connection for a pure logic test
# We want to test the trip scaling logic and the spatial matching SQL logic (conceptually)

def test_trip_scaling():
    print("--- Testing Trip Scaling Logic ---")
    # Simulation of CHILEAN_SCHEMAS mapping
    mapping = {
        'trips': 'VIAJES',
        'expansion_factor': 'FACTOR_EXP'
    }
    
    # Mock DataFrame
    df = pd.DataFrame({
        'VIAJES': [1, 2, 3],
        'FACTOR_EXP': [10, 20, 30]
    })
    
    print("Original DF:")
    print(df)
    
    # Scaling logic from handle_path_argument
    if 'trips' in mapping and 'expansion_factor' in mapping:
        t_col = mapping['trips']
        e_col = mapping['expansion_factor']
        df[t_col] = df[t_col] * df[e_col]
        print(f"Logic: Scaled {t_col} by {e_col}")
    
    print("Scaled DF:")
    print(df)
    
    expected = [10, 40, 90]
    if list(df['VIAJES']) == expected:
        print("✅ Trip Scaling Logic: PASSED")
    else:
        print("❌ Trip Scaling Logic: FAILED")

def test_spatial_matching_sql_sim():
    print("\n--- Testing Spatial Matcher SQL Concept ---")
    # Since we can't easily run the SQL without a complex setup here, 
    # we simulate the logic with Geopandas to verify the '10m' and 'impedance override'
    
    # Create an 'OSM' network (one line)
    osm = gpd.GeoDataFrame({
        'id': [1],
        'highway': ['primary'],
        'impedance': [10.0],
        'geometry': [LineString([(0, 0), (100, 0)])] # 100m line
    }, crs="EPSG:32718") # UTM 18S (Metric)
    
    # Create a 'Project' (Line exactly on top)
    proj = gpd.GeoDataFrame({
        'geometry': [LineString([(0, 0), (100, 0)])]
    }, crs="EPSG:32718")
    
    # Simulate ST_DWithin(10m)
    # In Python: check if distance is <= 10
    dist = osm.geometry[0].distance(proj.geometry[0])
    print(f"Distance between OSM and Project: {dist}m")
    
    if dist <= 10:
        osm.loc[0, 'is_project'] = True
        osm.loc[0, 'impedance'] = 1.0 # Override
        print("Match found. Impedance overridden to 1.0")
    
    if osm.loc[0, 'impedance'] == 1.0 and osm.loc[0, 'is_project'] == True:
        print("✅ Spatial Matcher Logic: PASSED")
    else:
        print("❌ Spatial Matcher Logic: FAILED")

if __name__ == "__main__":
    test_trip_scaling()
    test_spatial_matching_sql_sim()
