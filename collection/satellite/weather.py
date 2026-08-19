import os
import json
import requests
import matplotlib.pyplot as plt

from dotenv import load_dotenv

load_dotenv()

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")

if not OPENWEATHER_API_KEY:
    raise RuntimeError(
        "OPENWEATHER_API_KEY is missing from your .env file."
    )


FARM_FILE = os.path.join(
    "data",
    "processed",
    "farm",
    "farm.json"
)

OUTPUT_DIR = os.path.join(
    "data",
    "processed",
    "weather"
)

WEATHER_FILE = os.path.join(
    OUTPUT_DIR,
    "weather.json"
)

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


if not os.path.exists(FARM_FILE):
    raise FileNotFoundError(
        "farm.json was not found.\n"
        "Expected location: data/processed/farm/farm.json"
    )


with open(
    FARM_FILE,
    "r",
    encoding="utf-8"
) as file:
    farm = json.load(file)


farm_id = farm["farm_id"]

centroid = farm.get(
    "centroid",
    {}
)

centroid_lat = centroid.get(
    "latitude"
)

centroid_lon = centroid.get(
    "longitude"
)


if centroid_lat is None or centroid_lon is None:
    raise ValueError(
        "Farm centroid latitude/longitude is missing in farm.json."
    )

print()
print("=" * 75)
print("                 AGRISHIELD WEATHER COLLECTOR")
print("=" * 75)

print()

print(
    f"Farm ID       : {farm_id}"
)

print(
    f"Latitude      : {centroid_lat:.8f}"
)

print(
    f"Longitude     : {centroid_lon:.8f}"
)



WEATHER_URL = (
    "https://api.openweathermap.org/data/2.5/weather"
)

params = {
    "lat": centroid_lat,
    "lon": centroid_lon,
    "appid": OPENWEATHER_API_KEY,
    "units": "metric"
}


print()
print(
    "Requesting weather data from OpenWeather..."
)


try:

    response = requests.get(
        WEATHER_URL,
        params=params,
        timeout=30
    )

except requests.RequestException as error:

    raise RuntimeError(
        f"Network error while contacting OpenWeather: {error}"
    )

if response.status_code != 200:

    print()
    print("❌ OpenWeather API request failed.")

    print(
        "HTTP status:",
        response.status_code
    )

    print()

    try:

        print(
            json.dumps(
                response.json(),
                indent=4
            )
        )

    except Exception:

        print(
            response.text
        )

    response.raise_for_status()


weather_data = response.json()

print(
    "✓ Weather data received"
)


main_data = weather_data.get(
    "main",
    {}
)

wind_data = weather_data.get(
    "wind",
    {}
)

cloud_data = weather_data.get(
    "clouds",
    {}
)

rain_data = weather_data.get(
    "rain",
    {}
)

weather_description = weather_data.get(
    "weather",
    []
)


weather_summary = {

    "farm_id": farm_id,

    "location": {

        "latitude": centroid_lat,

        "longitude": centroid_lon,

        "city": weather_data.get(
            "name"
        ),

        "country": weather_data.get(
            "sys",
            {}
        ).get(
            "country"
        )
    },

    "timestamp": weather_data.get(
        "dt"
    ),

    "timezone_offset_seconds": weather_data.get(
        "timezone"
    ),

    "weather": {

        "condition": (
            weather_description[0].get("main")
            if weather_description
            else None
        ),

        "description": (
            weather_description[0].get("description")
            if weather_description
            else None
        ),

        "icon": (
            weather_description[0].get("icon")
            if weather_description
            else None
        )
    },

    "temperature": {

        "current_celsius": main_data.get(
            "temp"
        ),

        "feels_like_celsius": main_data.get(
            "feels_like"
        ),

        "minimum_celsius": main_data.get(
            "temp_min"
        ),

        "maximum_celsius": main_data.get(
            "temp_max"
        )
    },

    "atmosphere": {

        "pressure_hpa": main_data.get(
            "pressure"
        ),

        "humidity_percent": main_data.get(
            "humidity"
        ),

        "visibility_meters": weather_data.get(
            "visibility"
        )
    },

    "wind": {

        "speed_mps": wind_data.get(
            "speed"
        ),

        "direction_degrees": wind_data.get(
            "deg"
        ),

        "gust_mps": wind_data.get(
            "gust"
        )
    },

    "clouds": {

        "coverage_percent": cloud_data.get(
            "all"
        )
    },

    "rain": {

        "last_1_hour_mm": rain_data.get(
            "1h",
            0
        ),

        "last_3_hours_mm": rain_data.get(
            "3h",
            0
        )
    },

    "sun": {

        "sunrise": weather_data.get(
            "sys",
            {}
        ).get(
            "sunrise"
        ),

        "sunset": weather_data.get(
            "sys",
            {}
        ).get(
            "sunset"
        )
    },

    "source": {

        "provider": "OpenWeather",

        "api": "Current Weather API"
    }
}


# ============================================================
# 12. SAVE WEATHER JSON
# ============================================================

with open(
    WEATHER_FILE,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        weather_summary,
        file,
        indent=4
    )


print()
print(
    f"✓ Weather JSON saved: {WEATHER_FILE}"
)


# ============================================================
# 13. PRINT WEATHER SUMMARY
# ============================================================

print()
print("=" * 75)
print("                    CURRENT WEATHER")
print("=" * 75)

print()

print(
    "Condition     :",
    weather_summary["weather"]["description"]
)

print(
    "Temperature    :",
    weather_summary["temperature"]["current_celsius"],
    "°C"
)

print(
    "Feels Like     :",
    weather_summary["temperature"]["feels_like_celsius"],
    "°C"
)

print(
    "Humidity       :",
    weather_summary["atmosphere"]["humidity_percent"],
    "%"
)

print(
    "Pressure       :",
    weather_summary["atmosphere"]["pressure_hpa"],
    "hPa"
)

print(
    "Wind Speed     :",
    weather_summary["wind"]["speed_mps"],
    "m/s"
)

print(
    "Wind Direction  :",
    weather_summary["wind"]["direction_degrees"],
    "°"
)

print(
    "Cloud Coverage :",
    weather_summary["clouds"]["coverage_percent"],
    "%"
)

print(
    "Rain (1h)      :",
    weather_summary["rain"]["last_1_hour_mm"],
    "mm"
)

print()

print("=" * 75)
print("             WEATHER COLLECTION COMPLETE")
print("=" * 75)

print()

print(
    "Farm ID:",
    farm_id
)

print(
    "Weather JSON:",
    WEATHER_FILE
)