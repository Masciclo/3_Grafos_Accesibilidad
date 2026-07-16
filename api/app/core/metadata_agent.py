# +Ciclo: AI Schema and Planning Parameter Translator 🚴‍♂️🤖

import os
import json
from google import genai
from google.genai import types
from typing import Optional
from pydantic import BaseModel, Field

class PlanningParameters(BaseModel):
    budget_meters: float = Field(description="The total length budget in meters for cycleway upgrades. Parse numerical values (e.g. 5km -> 5000).")
    max_components: int = Field(description="The maximum number of disconnected project clusters to build (default: 1 for corridors, more for decentralized patches).")
    min_segment_length: float = Field(description="Minimum segment upgrade length in meters (default: 0.0). Keep it 0.0 unless the prompt explicitly specifies a minimum length.")
    max_segment_length: float = Field(description="Maximum segment upgrade length in meters (default: 2000).")
    osm_poi_types: list[str] = Field(description="List of target OSM tags to search for (e.g., ['school', 'park', 'university', 'hospital', 'bus_station']).")
    targeted_locations: list[str] = Field(default=[], description="List of target neighborhoods, suburbs, or landmarks mentioned in the prompt (e.g., ['centro', 'sur']).")

class OverpassQuery(BaseModel):
    query: str = Field(description="The exact Overpass QL query targeting the requested POIs. MUST output JSON and use the placeholder [bbox:{{bbox}}]. Do NOT specify hardcoded coordinate bounds.")

import time

def generate_content_with_retry(client, **kwargs):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            return client.models.generate_content(**kwargs)
        except Exception as e:
            error_str = str(e).lower()
            is_retryable = (
                "connection" in error_str or 
                "eof" in error_str or 
                "ssl" in error_str or 
                "connecterror" in error_str or 
                "unexpected_eof" in error_str or
                "503" in error_str or
                "500" in error_str or
                "429" in error_str or
                "unavailable" in error_str or
                "rate limit" in error_str or
                "servererror" in error_str or
                "apierror" in error_str
            )
            if is_retryable:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"\n[Warning] Gemini API/Network glitch encountered ({e}). Retrying in {wait_time}s... (Attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
            raise e

class MetadataAgent:
    def __init__(self):
        # The SDK automatically uses GEMINI_API_KEY from environment
        self.client = genai.Client()

    def parse_recommendation_prompt(self, prompt: str) -> PlanningParameters:
        """
        Parses the planner's qualitative prompt into quantitative parameters using Gemini.
        """
        system_instructions = """
        You are an expert urban active-mobility planning agent. Your task is to parse a qualitative
        infrastructure recommendation prompt into structured optimization parameters.
        Default values if not specified:
        - budget_meters: 3000
        - max_components: 1 (focus on a single continuous corridor unless multiple projects are requested)
        - min_segment_length: 0.0
        - max_segment_length: 2000
        - osm_poi_types: [] (empty list if no specific POI types like schools, parks, or plazas are mentioned)
        - targeted_locations: [] (empty list if no neighborhood, landmark, or specific suburb names are mentioned)
        """
        
        try:
            response = generate_content_with_retry(
                self.client,
                model='gemini-2.5-flash',
                contents=f"Prompt: {prompt}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instructions,
                    response_mime_type="application/json",
                    response_schema=PlanningParameters,
                    temperature=0.0
                )
            )
            params = PlanningParameters.model_validate_json(response.text)
            return params
        except Exception as e:
            print(f"[MetadataAgent Error] Prompt parsing failed: {e}")
            # Return safe defaults
            return PlanningParameters(
                budget_meters=3000.0,
                max_components=1,
                min_segment_length=0.0,
                max_segment_length=2000.0,
                osm_poi_types=[],
            )

    def generate_overpass_query(self, poi_types: list[str], locations: list[str] = None) -> str:
        """
        Generates an Overpass QL query string based on target POI types and spatial locations.
        """
        if not poi_types and not locations:
            return ""
            
        system_instructions = f"""
        Generate an Overpass QL query string to download nodes, ways, or relations for target POI types: {poi_types} and locations/neighborhoods: {locations}.
        Rules:
        - The query MUST start with [out:json][timeout:25][bbox:{{bbox}}];
        - Do NOT specify bounding box filters inside individual clauses (i.e. do NOT use ([bbox:{{bbox}}]) on node/way/relation lines).
        - For POIs, use standard keys: amenity, leisure, landuse, tourism, or public_transport.
        - For locations/neighborhoods/suburbs (e.g. ['centro', 'sur']), query nodes or ways matching place=suburb, place=neighbourhood, place=quarter or place=town with name search (case-insensitive regex, e.g. name~"centro|sur",i).
        - Combine everything in a single union block.
        - Return ONLY the exact Overpass query matching the response schema.
        
        Example Output for ['school'] and ['centro', 'sur']:
        [out:json][timeout:25][bbox:{{bbox}}];
        (
          node["amenity"="school"];
          way["amenity"="school"];
          node["place"~"suburb|neighbourhood|quarter"]["name"~"centro|sur",i];
        );
        out center;
        """
        
        try:
            response = generate_content_with_retry(
                self.client,
                model='gemini-2.5-flash',
                contents=f"Generate query for POI types: {poi_types} and locations: {locations}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instructions,
                    response_mime_type="application/json",
                    response_schema=OverpassQuery,
                    temperature=0.0
                )
            )
            query_obj = OverpassQuery.model_validate_json(response.text)
            return query_obj.query
        except Exception as e:
            print(f"[MetadataAgent Error] Overpass query generation failed: {e}")
            # Safe generic query fallback utilizing global header bbox
            fallback_query = "[out:json][timeout:25][bbox:{bbox}];\n(\n"
            if poi_types:
                for t in poi_types:
                    fallback_query += f'  node["amenity"="{t}"];\n  way["amenity"="{t}"];\n'
                    fallback_query += f'  node["leisure"="{t}"];\n  way["leisure"="{t}"];\n'
            if locations:
                locs_regex = "|".join(locations)
                fallback_query += f'  node["place"~"suburb|neighbourhood|quarter"]["name"~"{locs_regex}",i];\n'
            fallback_query += ");\nout center;"
            return fallback_query

class HighwayMultiplier(BaseModel):
    highway_type: str = Field(description="Highway type name, e.g., 'primary', 'secondary', 'tertiary', 'residential'")
    multiplier: float = Field(description="The impedance multiplier value (e.g. 0.5, 1.5, 3.0)")

class LocationOrientation(BaseModel):
    seed_target: str = Field(description="The starting point (neighborhood, park, intersection).")
    gravity_attractor: str = Field(default="", description="The destination to head towards. Leave empty if none.")

class ProjectConfig(BaseModel):
    num_projects: int = Field(default=1, description="Number of distinct routes requested.")
    budget_meters: float = Field(description="Length limit for each project in meters.")
    highway_lambdas: list[HighwayMultiplier] = Field(description="List of street preference multipliers (e.g., [{'highway_type': 'primary', 'multiplier': 2.0}, {'highway_type': 'residential', 'multiplier': 0.5}]).")
    location_and_orientation: LocationOrientation

class GrillSessionTurn(BaseModel):
    status: str = Field(description="Must be 'ASK' if more details are needed, or 'COMPLETE' if we have sufficient info to define the project.")
    next_question: Optional[str] = Field(None, description="The next natural, friendly question in Spanish to ask the user.")
    config: Optional[ProjectConfig] = Field(None, description="Only fill this when status is 'COMPLETE'. The finalized project configuration.")

class InteractiveGrillAgent:
    def __init__(self):
        self.client = genai.Client()
        self.agents_dir = os.path.join(os.path.dirname(__file__), "agents")

    def _load_prompt(self, filename: str) -> str:
        path = os.path.join(self.agents_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def grill_turn(self, messages_history: list[dict]) -> GrillSessionTurn:
        system_instruction = self._load_prompt("grill_consolidado.md")
        
        contents = []
        for msg in messages_history:
            role = msg["role"]
            content_text = msg["content"]
            contents.append(f"{role.capitalize()}: {content_text}")
        
        prompt_content = "\n".join(contents)
        
        response = generate_content_with_retry(
            self.client,
            model='gemini-2.5-flash',
            contents=prompt_content,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=GrillSessionTurn,
                temperature=0.2
            )
        )
        return GrillSessionTurn.model_validate_json(response.text)



