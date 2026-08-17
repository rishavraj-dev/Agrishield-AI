import os
import json
import requests
from dotenv import load_dotenv

# ==========================================
# CONFIGURATION & SETUP
# ==========================================
load_dotenv()
SOILHIVE_TOKEN = os.getenv("SOILHIVE_TOKEN")

if not SOILHIVE_TOKEN:
    raise RuntimeError("❌ SOILHIVE_TOKEN is missing from .env")

# Define paths based on your project structure
FARM_FILE = os.path.join("data", "processed", "farm", "farm.json")
OUTPUT_DIR = os.path.join("data", "processed", "soil")
SOIL_FILE = os.path.join(OUTPUT_DIR, "soil_data.json")

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Verified global dataset IDs that work for India
INDIA_DATASET_IDS = [1, 4, 8, 19, 20, 21, 38]

# ==========================================
# 1. LOAD FARM DATA & CONVERT TO WKT
# ==========================================
print("=" * 60)
print("           AGRISHIELD SOIL DATA COLLECTOR")
print("=" * 60)

if not os.path.exists(FARM_FILE):
    raise FileNotFoundError(f"❌ Farm file not found at: {FARM_FILE}")

print("Loading farm boundary...")
with open(FARM_FILE, "r", encoding="utf-8") as file:
    farm = json.load(file)

farm_id = farm.get("farm_id", "UNKNOWN_FARM")
centroid = farm.get("centroid", {})
latitude = centroid.get("latitude")
longitude = centroid.get("longitude")

# Extract the polygon coordinates and convert to WKT (Well-Known Text)
try:
    polygon_coords = farm["geometry"]["coordinates"][0]
    wkt_points = [f"{lon} {lat}" for lon, lat in polygon_coords]
    wkt_geometry = f"POLYGON (({', '.join(wkt_points)}))"
except (KeyError, IndexError) as e:
    raise ValueError(f"❌ Invalid geometry in farm.json: {e}")

print(f"Farm ID   : {farm_id}")
print(f"Centroid  : {latitude}, {longitude}")
print("Geometry  : Successfully extracted WKT Polygon\n")

# ==========================================
# 2. FETCH SOIL DATA FROM SOILHIVE
# ==========================================
BASE_URL = "https://api.soilhive.ag/v1"
SOIL_DATA_URL = f"{BASE_URL}/soil-data-by-geometry"

headers = {
    "Authorization": f"Bearer {SOILHIVE_TOKEN}",
    "Accept": "application/ld+json",
    "Content-Type": "application/json"
}

request_body = {
    "geometry": wkt_geometry,
    "datasets": INDIA_DATASET_IDS
}

print(f"Fetching soil data from {len(INDIA_DATASET_IDS)} global datasets...")

try:
    response = requests.post(SOIL_DATA_URL, headers=headers, json=request_body, timeout=120)
    response.raise_for_status()
    data = response.json()
    
    feed_elements = data.get("dataFeedElement", [])
    
    if not feed_elements:
        print("❌ API returned a successful response, but no soil data was found for this polygon.")
        exit()
        
    print(f"✅ Success! Extracted {len(feed_elements)} raw soil data items.\n")

# ==========================================
# 3. CLEAN & FORMAT DATA (SIMPLIFIED)
# ==========================================
    print("Cleaning and standardizing properties...")
    clean_soil_data = {}

    for element in feed_elements:
        item_list = element.get("item", [])
        
        prop_name = None
        prop_value = None
        unit = ""
        
        for prop in item_list:
            name = prop.get("name")
            
            if name == "Property":
                prop_name = prop.get("value")
            elif name == "Conversion" and "value" in prop:
                prop_value = prop.get("value")
                unit = prop.get("unitText", "")
            elif name == "Value" and prop_value is None:
                prop_value = prop.get("value")
                unit = prop.get("unitText", "")

        if prop_name and prop_value is not None:
            # Clean up excessively long OpenLandMap properties
            if prop_name.startswith("sol_"):
                parts = prop_name.split("_")
                try:
                    # Extract the core name (e.g., 'bulkdens')
                    base_name = parts[1].split(".")[0] 
                    # Extract the depth (e.g., '0..0cm' -> '0-0cm')
                    depth_part = next(p for p in parts if p.startswith("b") and "cm" in p)
                    depth = depth_part.replace("b", "").replace("..", "-")
                    prop_name = f"{base_name}_{depth}"
                except StopIteration:
                    pass

            # Save strictly the property name and the value
            # Note: We don't overwrite if the key already exists to prevent duplicate depths
            if prop_name not in clean_soil_data:
                clean_soil_data[prop_name] = f"{prop_value} {unit}".strip()

# ==========================================
# 4. SAVE FINAL JSON
# ==========================================
    final_output = {
        "farm_id": farm_id,
        "location": centroid,
        "soil_properties": clean_soil_data
    }

    with open(SOIL_FILE, "w", encoding="utf-8") as file:
        json.dump(final_output, file, indent=4)

    print("=" * 60)
    print("                 PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Data saved to: {SOIL_FILE}")
    print("\nPreview of simplified output:")
    print(json.dumps(clean_soil_data, indent=4))

except requests.exceptions.RequestException as e:
    print("\n❌ API Request Failed!")
    print(f"Error: {e}")
    if 'response' in locals() and response is not None:
        print(f"Server Response: {response.text}")