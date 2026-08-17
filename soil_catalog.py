import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
SOILHIVE_TOKEN = os.getenv("SOILHIVE_TOKEN")

BASE_URL = "https://api.soilhive.ag/v1"
headers = {
    "Authorization": f"Bearer {SOILHIVE_TOKEN}",
    "Accept": "application/ld+json"
}

print("Fetching SoilHive dataset catalog...\n")

try:
    response = requests.get(f"{BASE_URL}/datasets", headers=headers, timeout=60)
    response.raise_for_status()
    data = response.json()
    
    # Dump the entire raw response into a file
    output_file = "soilhive_catalog.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    print(f"✅ Success! Catalog saved to: {output_file}")
    print("Go open this file in VS Code and hit Ctrl+F to search!")

except Exception as e:
    print(f"❌ Failed to fetch catalog: {e}")