import os
import json
import requests

import numpy as np
import rasterio
import matplotlib.pyplot as plt

from dotenv import load_dotenv


# ============================================================
# AGRISHIELD - FARM SATELLITE ANALYSIS
#
# Reads:
#     farm/farm.json
#
# Sentinel-2:
#     B02 = Blue
#     B03 = Green
#     B04 = Red
#     B08 = NIR
#     B11 = SWIR
#     SCL = Scene Classification Layer
#
# Calculates:
#     NDVI = (B08 - B04) / (B08 + B04)
#     NDWI = (B03 - B08) / (B03 + B08)
#     NDMI = (B08 - B11) / (B08 + B11)
#
# Produces:
#     True-color farm image
#     NDVI overlay
#     NDWI overlay
#     NDMI overlay
#     NDVI/NDWI/NDMI GeoTIFFs
#     Statistics JSON
# ============================================================


# ============================================================
# 1. LOAD ENVIRONMENT
# ============================================================

load_dotenv()

CLIENT_ID = os.getenv("COPERNICUS_CLIENT_ID")
CLIENT_SECRET = os.getenv("COPERNICUS_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    raise RuntimeError(
        "COPERNICUS_CLIENT_ID or COPERNICUS_CLIENT_SECRET "
        "is missing from your .env file."
    )


# ============================================================
# 2. FILE PATHS
# ============================================================

FARM_FILE = os.path.join(
    "data", "processed", "farm", "farm.json"
)

OUTPUT_DIR = os.path.join("data", "processed", "satellite", "output")

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True
)


if not os.path.exists(FARM_FILE):
    raise FileNotFoundError(
        "farm/farm.json was not found.\n"
        "Run Farmer.py first."
    )


# ============================================================
# 3. LOAD FARM
# ============================================================

with open(
    FARM_FILE,
    "r",
    encoding="utf-8"
) as file:
    farm = json.load(file)


# ------------------------------------------------------------
# New Farmer.py structure:
#
# farm["farm_id"]
# farm["points"]
# farm["geometry"]
# farm["area"]
# farm["perimeter"]
# farm["centroid"]
# farm["bounding_box"]
# ------------------------------------------------------------

farm_id = farm["farm_id"]

farm_geometry = farm["geometry"]

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


# ============================================================
# 4. ANALYSIS PERIOD
# ============================================================

ANALYSIS_FROM = "2026-07-01T00:00:00Z"
ANALYSIS_TO = "2026-08-15T23:59:59Z"


# ============================================================
# 5. PRINT FARM INFORMATION
# ============================================================

print()
print("=" * 75)
print("                 AGRISHIELD SATELLITE ANALYSIS")
print("=" * 75)

print()

print(
    f"Farm ID       : {farm_id}"
)

print(
    f"Boundary pts  : {farm.get('point_count', 'N/A')}"
)


if centroid_lat is not None and centroid_lon is not None:

    print(
        f"Centroid      : "
        f"{centroid_lat:.8f}, "
        f"{centroid_lon:.8f}"
    )

else:

    print(
        "Centroid      : Not available"
    )


# ------------------------------------------------------------
# Area information
# ------------------------------------------------------------

area_data = farm.get(
    "area",
    {}
)

if area_data:

    print(
        f"Area          : "
        f"{area_data.get('square_meters', 0):,.2f} m²"
    )

    print(
        f"Area          : "
        f"{area_data.get('hectares', 0):.4f} ha"
    )

    print(
        f"Area          : "
        f"{area_data.get('acres', 0):.4f} acres"
    )


# ------------------------------------------------------------
# Perimeter information
# ------------------------------------------------------------

perimeter_data = farm.get(
    "perimeter",
    {}
)

if perimeter_data:

    print(
        f"Perimeter     : "
        f"{perimeter_data.get('meters', 0):,.2f} m"
    )


print()
print("Analysis period:")
print(f"From          : {ANALYSIS_FROM}")
print(f"To            : {ANALYSIS_TO}")


# ============================================================
# 6. CHECK FARM GEOMETRY
# ============================================================

if (
    not isinstance(farm_geometry, dict)
    or farm_geometry.get("type") != "Polygon"
    or "coordinates" not in farm_geometry
):

    raise ValueError(
        "Invalid farm geometry in farm/farm.json."
    )


coordinates = farm_geometry["coordinates"][0]

if len(coordinates) < 4:

    raise ValueError(
        "Farm polygon must contain at least "
        "3 boundary points plus the closing point."
    )


# ============================================================
# 6. COPERNICUS ENDPOINTS
# ============================================================

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

PROCESS_URL = (
    "https://sh.dataspace.copernicus.eu/"
    "process/v1"
)


# ============================================================
# 7. AUTHENTICATION
# ============================================================

def get_access_token():

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        timeout=30,
    )

    if response.status_code != 200:

        print(
            "\n❌ Authentication failed."
        )

        print(
            "HTTP status:",
            response.status_code
        )

        print(
            response.text
        )

    response.raise_for_status()

    return response.json()["access_token"]


print()
print(
    "Authenticating with Copernicus..."
)

token = get_access_token()

print(
    "✓ Copernicus authentication successful"
)


# ============================================================
# 8. EVALSCRIPT
# ============================================================
#
# ONE Sentinel-2 input dataset.
#
# B02 = Blue
# B03 = Green
# B04 = Red
# B08 = NIR
# B11 = SWIR
# SCL = Scene Classification
#
# All requested as DN.
#
# NDVI/NDWI/NDMI are calculated locally in Python.
# ============================================================

evalscript = """
//VERSION=3

function setup() {

    return {

        input: [

            {
                bands: [
                    "B02",
                    "B03",
                    "B04",
                    "B08",
                    "B11",
                    "SCL"
                ],

                units: "DN"
            }

        ],

        output: {

            bands: 6,

            sampleType:
                SampleType.FLOAT32
        }
    };
}


function evaluatePixel(sample) {

    return [

        sample.B02,
        sample.B03,
        sample.B04,
        sample.B08,
        sample.B11,
        sample.SCL

    ];
}
"""


# ============================================================
# 9. SENTINEL-2 REQUEST
# ============================================================
#
# Current testing period:
#     2026-07-01 -> 2026-08-15
#
# leastCC = least-cloudy acquisition.
# ============================================================

request_body = {

    "input": {

        "bounds": {

            "properties": {

                "crs":
                "http://www.opengis.net/def/crs/"
                "OGC/1.3/CRS84"
            },

            "geometry":
            farm_geometry
        },


        "data": [

            {

                "type":
                "sentinel-2-l2a",

                "dataFilter": {

                    "timeRange": {

                        "from":
                        ANALYSIS_FROM,

                        "to":
                        ANALYSIS_TO
                    },

                    "maxCloudCoverage":
                    80,

                    "mosaickingOrder":
                    "leastCC"
                },

                "processing": {

                    "harmonizeValues":
                    "true"
                }
            }

        ]
    },


    "output": {

        "width":
        700,

        "height":
        700,

        "responses": [

            {

                "identifier":
                "default",

                "format": {

                    "type":
                    "image/tiff"
                }
            }

        ]
    },


    "evalscript":
    evalscript
}


# ============================================================
# 10. REQUEST SENTINEL-2
# ============================================================

print()
print(
    "Requesting Sentinel-2 data..."
)


try:

    response = requests.post(

        PROCESS_URL,

        headers={

            "Authorization":
            f"Bearer {token}",

            "Content-Type":
            "application/json",

            "Accept":
            "image/tiff"
        },

        json=request_body,

        timeout=180
    )

except requests.RequestException as error:

    raise RuntimeError(
        f"Network error while contacting Copernicus: {error}"
    )


# ============================================================
# 11. HANDLE API ERROR
# ============================================================

if response.status_code != 200:

    print()
    print(
        "❌ Copernicus API request failed."
    )

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


print(
    "✓ Sentinel-2 data received"
)


# ============================================================
# 12. SAVE RAW DATA
# ============================================================

raw_file = os.path.join(
    OUTPUT_DIR,
    "sentinel_raw.tif"
)

with open(
    raw_file,
    "wb"
) as file:

    file.write(
        response.content
    )

print(
    f"✓ Saved: {raw_file}"
)


# ============================================================
# 13. READ TIFF
# ============================================================

with rasterio.open(
    raw_file
) as src:

    raw = src.read()

    profile = src.profile

    transform = src.transform

    crs = src.crs

    width = src.width

    height = src.height


print()
print(
    "========== RASTER INFORMATION =========="
)

print(
    "Shape:",
    raw.shape
)

print(
    "Width:",
    width
)

print(
    "Height:",
    height
)

print(
    "CRS:",
    crs
)


# ============================================================
# 14. CHECK BAND COUNT
# ============================================================

if raw.shape[0] != 6:

    raise RuntimeError(
        f"Expected 6 bands but received "
        f"{raw.shape[0]}."
    )


# ============================================================
# 15. EXTRACT BANDS
# ============================================================

blue = raw[0].astype(
    np.float32
)

green = raw[1].astype(
    np.float32
)

red = raw[2].astype(
    np.float32
)

nir = raw[3].astype(
    np.float32
)

swir = raw[4].astype(
    np.float32
)

scl = np.rint(
    raw[5]
).astype(
    np.int16
)


# ============================================================
# 16. RAW BAND INFORMATION
# ============================================================

print()
print(
    "========== RAW SENTINEL BANDS =========="
)

print(
    f"B02 Blue  : "
    f"{np.nanmin(blue):.2f} -> "
    f"{np.nanmax(blue):.2f}"
)

print(
    f"B03 Green : "
    f"{np.nanmin(green):.2f} -> "
    f"{np.nanmax(green):.2f}"
)

print(
    f"B04 Red   : "
    f"{np.nanmin(red):.2f} -> "
    f"{np.nanmax(red):.2f}"
)

print(
    f"B08 NIR   : "
    f"{np.nanmin(nir):.2f} -> "
    f"{np.nanmax(nir):.2f}"
)

print(
    f"B11 SWIR  : "
    f"{np.nanmin(swir):.2f} -> "
    f"{np.nanmax(swir):.2f}"
)


# ============================================================
# 17. SCL CLASSES
# ============================================================

scl_classes = {

    0: "No Data",
    1: "Saturated / Defective",
    2: "Dark Area / Shadows",
    3: "Cloud Shadow",
    4: "Vegetation",
    5: "Bare Soil",
    6: "Water",
    7: "Low Probability Cloud / Unclassified",
    8: "Medium Probability Cloud",
    9: "High Probability Cloud",
    10: "Cirrus",
    11: "Snow / Ice"
}


unique_scl, counts = np.unique(
    scl,
    return_counts=True
)


print()
print(
    "========== SCL CLASSES =========="
)


for class_id, count in zip(
    unique_scl,
    counts
):

    class_name = scl_classes.get(
        int(class_id),
        "Unknown"
    )

    percentage = (
        count / scl.size
    ) * 100

    print(
        f"SCL {int(class_id):>2} | "
        f"{class_name:<35} | "
        f"{count:>8} pixels | "
        f"{percentage:6.2f}%"
    )


# ============================================================
# 18. CLOUD / INVALID MASK
# ============================================================

bad_classes = np.array(
    [
        0,   # No Data
        1,   # Saturated
        3,   # Cloud shadow
        8,   # Medium cloud
        9,   # High cloud
        10,  # Cirrus
        11   # Snow / ice
    ],
    dtype=np.int16
)


bad_mask = np.isin(
    scl,
    bad_classes
)


valid_mask = ~bad_mask


valid_count = np.count_nonzero(
    valid_mask
)

invalid_count = np.count_nonzero(
    bad_mask
)


print()
print(
    "========== CLOUD MASK =========="
)

print(
    "Total pixels:",
    scl.size
)

print(
    "Valid pixels:",
    valid_count
)

print(
    "Removed pixels:",
    invalid_count
)

print(
    "Valid percentage:",
    f"{100 * valid_count / scl.size:.2f}%"
)


if valid_count == 0:

    raise RuntimeError(
        "\nNo valid pixels remain after cloud masking.\n"
        "Try a wider/different date range."
    )


# ============================================================
# 19. NDVI
#
# NDVI = (NIR - RED) / (NIR + RED)
# ============================================================

ndvi = np.full(
    nir.shape,
    np.nan,
    dtype=np.float32
)


ndvi_denominator = (
    nir + red
)


mask = (
    valid_mask
    &
    np.isfinite(
        ndvi_denominator
    )
    &
    (
        ndvi_denominator != 0
    )
)


ndvi[mask] = (

    (
        nir[mask]
        -
        red[mask]
    )

    /

    ndvi_denominator[mask]
)


# ============================================================
# 20. NDWI
#
# NDWI = (GREEN - NIR) / (GREEN + NIR)
# ============================================================

ndwi = np.full(
    nir.shape,
    np.nan,
    dtype=np.float32
)


ndwi_denominator = (
    green + nir
)


mask = (
    valid_mask
    &
    np.isfinite(
        ndwi_denominator
    )
    &
    (
        ndwi_denominator != 0
    )
)


ndwi[mask] = (

    (
        green[mask]
        -
        nir[mask]
    )

    /

    ndwi_denominator[mask]
)


# ============================================================
# 21. NDMI
#
# NDMI = (NIR - SWIR) / (NIR + SWIR)
# ============================================================

ndmi = np.full(
    nir.shape,
    np.nan,
    dtype=np.float32
)


ndmi_denominator = (
    nir + swir
)


mask = (
    valid_mask
    &
    np.isfinite(
        ndmi_denominator
    )
    &
    (
        ndmi_denominator != 0
    )
)


ndmi[mask] = (

    (
        nir[mask]
        -
        swir[mask]
    )

    /

    ndmi_denominator[mask]
)


# ============================================================
# 22. STATISTICS FUNCTION
# ============================================================

def calculate_statistics(
    name,
    data
):

    values = data[
        np.isfinite(data)
    ]

    print()
    print(
        f"========== {name} =========="
    )

    print(
        "Total pixels:",
        data.size
    )

    print(
        "Valid pixels:",
        values.size
    )

    if values.size == 0:

        print(
            "❌ No valid values."
        )

        return None

    result = {

        "mean":
        float(np.mean(values)),

        "median":
        float(np.median(values)),

        "min":
        float(np.min(values)),

        "max":
        float(np.max(values)),

        "std":
        float(np.std(values))
    }

    print(
        f"Mean   : {result['mean']:.4f}"
    )

    print(
        f"Median : {result['median']:.4f}"
    )

    print(
        f"Min    : {result['min']:.4f}"
    )

    print(
        f"Max    : {result['max']:.4f}"
    )

    print(
        f"Std    : {result['std']:.4f}"
    )

    return result


# ============================================================
# 23. STATISTICS
# ============================================================

ndvi_stats = calculate_statistics(
    "NDVI",
    ndvi
)

ndwi_stats = calculate_statistics(
    "NDWI",
    ndwi
)

ndmi_stats = calculate_statistics(
    "NDMI",
    ndmi
)


# ============================================================
# 24. TRUE-COLOR RGB
#
# B04 = Red
# B03 = Green
# B02 = Blue
#
# This is DISPLAY processing, not scientific reflectance
# processing.
# ============================================================

rgb = np.stack(
    [
        red,
        green,
        blue
    ],
    axis=-1
).astype(
    np.float32
)


# Convert DN to approximate reflectance for display
rgb = rgb / 10000.0


# Simple visualization stretch
rgb = np.clip(
    rgb * 2.5,
    0,
    1
)


# Hide cloud pixels from the background
rgb_display = rgb.copy()


rgb_display[
    bad_mask
] = np.nan


# ============================================================
# 25. FARM BOUNDARY
# ============================================================

polygon_x = [
    point[0]
    for point in coordinates
]

polygon_y = [
    point[1]
    for point in coordinates
]


# ============================================================
# 26. RASTER GEOGRAPHIC EXTENT
# ============================================================

left = transform.c

top = transform.f

right = (
    left
    +
    transform.a * width
)

bottom = (
    top
    +
    transform.e * height
)


extent = [
    left,
    right,
    bottom,
    top
]


# ============================================================
# 27. FARM TRUE-COLOR MAP
# ============================================================

true_color_file = os.path.join(
    OUTPUT_DIR,
    "farm_true_color.png"
)


plt.figure(
    figsize=(11, 9)
)


plt.imshow(
    rgb_display,
    extent=extent
)


# Farm boundary
plt.plot(
    polygon_x,
    polygon_y,
    linewidth=3
)


# P1, P2, P3...
for i, point in enumerate(
    coordinates[:-1],
    start=1
):

    plt.annotate(
        f"P{i}",
        (
            point[0],
            point[1]
        ),
        xytext=(6, 6),
        textcoords="offset points",
        fontsize=10,
        fontweight="bold"
    )


plt.title(
    f"AgriShield - Farm True Color\n{farm_id}\nAnalysis: {ANALYSIS_FROM[:10]} → {ANALYSIS_TO[:10]}"
)


plt.xlabel(
    "Longitude"
)

plt.ylabel(
    "Latitude"
)


plt.grid(
    alpha=0.2
)


plt.tight_layout()


plt.savefig(
    true_color_file,
    dpi=200,
    bbox_inches="tight"
)


plt.show()


# ============================================================
# 28. INDEX OVERLAY FUNCTION
# ============================================================

def create_overlay_map(
    data,
    index_name,
    colormap,
    filename
):

    output_file = os.path.join(
        OUTPUT_DIR,
        filename
    )


    plt.figure(
        figsize=(11, 9)
    )


    # --------------------------------------------------------
    # Satellite true-color background
    # --------------------------------------------------------

    plt.imshow(
        rgb_display,
        extent=extent
    )


    # --------------------------------------------------------
    # Index overlay
    # --------------------------------------------------------

    image = plt.imshow(

        data,

        extent=extent,

        vmin=-1,

        vmax=1,

        cmap=colormap,

        alpha=0.68
    )


    # --------------------------------------------------------
    # Farm outline
    # --------------------------------------------------------

    plt.plot(
        polygon_x,
        polygon_y,
        linewidth=3
    )


    # --------------------------------------------------------
    # Point labels
    # --------------------------------------------------------

    for i, point in enumerate(
        coordinates[:-1],
        start=1
    ):

        plt.annotate(
            f"P{i}",
            (
                point[0],
                point[1]
            ),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold"
        )


    # --------------------------------------------------------
    # Color bar
    # --------------------------------------------------------

    colorbar = plt.colorbar(
        image
    )

    colorbar.set_label(
        index_name
    )


    # --------------------------------------------------------
    # Title
    # --------------------------------------------------------

    plt.title(
        f"AgriShield - {index_name} Farm Analysis\n"
        f"{farm_id}\n"
        f"Analysis: {ANALYSIS_FROM[:10]} → {ANALYSIS_TO[:10]}"
    )


    plt.xlabel(
        "Longitude"
    )

    plt.ylabel(
        "Latitude"
    )


    plt.grid(
        alpha=0.2
    )


    plt.tight_layout()


    plt.savefig(
        output_file,
        dpi=200,
        bbox_inches="tight"
    )


    plt.show()


    return output_file


# ============================================================
# 29. CREATE INDEX MAPS
# ============================================================

print()
print(
    "Creating farm maps..."
)


ndvi_map_file = create_overlay_map(

    ndvi,

    "NDVI",

    "RdYlGn",

    "ndvi_farm_overlay.png"
)


ndwi_map_file = create_overlay_map(

    ndwi,

    "NDWI",

    "BrBG",

    "ndwi_farm_overlay.png"
)


ndmi_map_file = create_overlay_map(

    ndmi,

    "NDMI",

    "YlGnBu",

    "ndmi_farm_overlay.png"
)


print(
    "✓ Farm maps created."
)


# ============================================================
# 30. SAVE GEOTIFF
# ============================================================

def save_geotiff(
    filename,
    data
):

    output_file = os.path.join(
        OUTPUT_DIR,
        filename
    )

    output_profile = profile.copy()

    output_profile.update(

        count=1,

        dtype="float32",

        compress="lzw"

    )


    with rasterio.open(

        output_file,

        "w",

        **output_profile

    ) as dst:

        dst.write(

            data.astype(
                np.float32
            ),

            1
        )


    return output_file


ndvi_tif = save_geotiff(
    "ndvi.tif",
    ndvi
)

ndwi_tif = save_geotiff(
    "ndwi.tif",
    ndwi
)

ndmi_tif = save_geotiff(
    "ndmi.tif",
    ndmi
)


print()
print(
    "✓ NDVI GeoTIFF:",
    ndvi_tif
)

print(
    "✓ NDWI GeoTIFF:",
    ndwi_tif
)

print(
    "✓ NDMI GeoTIFF:",
    ndmi_tif
)


# ============================================================
# 31. SAVE SUMMARY JSON
# ============================================================

summary = {

    "farm_id":
    farm_id,

    "analysis_period": {
        "from": ANALYSIS_FROM,
        "to": ANALYSIS_TO
    },

    "point_count":
    farm.get(
        "point_count"
    ),

    "area":
    farm.get(
        "area"
    ),

    "perimeter":
    farm.get(
        "perimeter"
    ),

    "centroid":
    farm.get(
        "centroid"
    ),

    "bounding_box":
    farm.get(
        "bounding_box"
    ),

    "indices": {

        "NDVI":
        ndvi_stats,

        "NDWI":
        ndwi_stats,

        "NDMI":
        ndmi_stats
    },

    "cloud_mask": {

        "total_pixels":
        int(
            scl.size
        ),

        "valid_pixels":
        int(
            valid_count
        ),

        "removed_pixels":
        int(
            invalid_count
        ),

        "valid_percentage":
        float(
            100 *
            valid_count /
            scl.size
        )
    },

    "scl_classes": {

        str(
            int(class_id)
        ):
        {

            "name":
            scl_classes.get(
                int(class_id),
                "Unknown"
            ),

            "pixels":
            int(count),

            "percentage":
            float(
                100 *
                count /
                scl.size
            )

        }

        for class_id, count
        in zip(
            unique_scl,
            counts
        )
    },

    "files": {

        "raw":
        raw_file,

        "true_color":
        true_color_file,

        "ndvi_tif":
        ndvi_tif,

        "ndwi_tif":
        ndwi_tif,

        "ndmi_tif":
        ndmi_tif,

        "ndvi_overlay":
        ndvi_map_file,

        "ndwi_overlay":
        ndwi_map_file,

        "ndmi_overlay":
        ndmi_map_file
    }
}


summary_file = os.path.join(
    OUTPUT_DIR,
    "analysis_summary.json"
)


with open(
    summary_file,
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        summary,
        file,
        indent=4
    )


# ============================================================
# 32. FINAL
# ============================================================

print()
print("=" * 75)
print("                   ANALYSIS COMPLETE")
print("=" * 75)

print()

print(
    "Farm ID:",
    farm_id
)

print(
    "Analysis period:",
    f"{ANALYSIS_FROM} → {ANALYSIS_TO}"
)

print()

print(
    "True Color Map:",
    true_color_file
)

print(
    "NDVI Overlay:",
    ndvi_map_file
)

print(
    "NDWI Overlay:",
    ndwi_map_file
)

print(
    "NDMI Overlay:",
    ndmi_map_file
)

print()

print(
    "Summary:",
    summary_file
)

print()

print(
    "✓ AgriShield satellite analysis complete."
)