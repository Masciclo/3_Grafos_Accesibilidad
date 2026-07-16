# +Ciclo: OSM Overpass API Client 🚴‍♂️🌐

import os
import json
import requests
from rich.console import Console

console = Console()

class OverpassClient:
    def __init__(self):
        self.endpoint = "https://overpass-api.de/api/interpreter"

    def download_pois(self, query: str, bbox: list, output_path: str) -> bool:
        """
        Executes an Overpass QL query within a bounding box and saves the result as GeoJSON.
        bbox format: [lon_min, lat_min, lon_max, lat_max]
        """
        if not query:
            return False
            
        # Overpass expects: (lat_min, lon_min, lat_max, lon_max)
        overpass_bbox = f"{bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]}"
        
        # Replace the bounding box placeholder (handle both single and double curly brace formats)
        formatted_query = query.replace("[bbox:{bbox}]", f"[bbox:{overpass_bbox}]")
        formatted_query = formatted_query.replace("[bbox:{{bbox}}]", f"[bbox:{overpass_bbox}]")
        
        console.print(f"[bold dim]Sending Overpass query with bbox: {overpass_bbox}...[/]")
        
        try:
            headers = {
                "User-Agent": "plus-ciclo-routing-agent/1.0 (contact: jaime.vergara@tudelft.nl)",
                "Accept-Charset": "utf-8"
            }
            response = requests.post(self.endpoint, data={"data": formatted_query}, headers=headers, timeout=30)
            if response.status_code != 200:
                console.print(f"[bold red]Overpass API Error:[/] HTTP status {response.status_code}: {response.text}")
                return False
                
            data = response.json()
            elements = data.get("elements", [])
            
            if not elements:
                console.print("[bold yellow]Warning: Overpass query returned 0 elements.[/]")
                return False
                
            # Parse OSM elements into a standard GeoJSON FeatureCollection
            features = []
            for el in elements:
                properties = el.get("tags", {})
                properties["osm_id"] = el.get("id")
                properties["osm_type"] = el.get("type")
                
                # Determine geometry
                lat = el.get("lat")
                lon = el.get("lon")
                
                # If way outputted center coords
                if not lat and "center" in el:
                    lat = el["center"].get("lat")
                    lon = el["center"].get("lon")
                    
                if lat is not None and lon is not None:
                    feature = {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(lon), float(lat)]
                        },
                        "properties": properties
                    }
                    features.append(feature)
            
            geojson = {
                "type": "FeatureCollection",
                "features": features
            }
            
            # Ensure parent directories exist
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(geojson, f, ensure_ascii=False, indent=2)
                
            console.print(f"[bold green]Successfully saved {len(features)} POIs to {output_path}[/]")
            return True
            
        except Exception as e:
            console.print(f"[bold red]Failed to download POIs from Overpass:[/] {e}")
            return False
