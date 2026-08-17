import os
import json
import re

import matplotlib.pyplot as plt

from shapely.geometry import Polygon
from pyproj import Geod


# ============================================================
# AGRISHIELD - FARM REGISTRATION
#
# Farmer enters:
#   P1, P2, P3, ... Pn
#
# Each point is:
#   Latitude, Longitude
#
# The script:
#   - validates coordinates
#   - creates a farm polygon
#   - calculates geodesic area
#   - calculates perimeter
#   - calculates centroid
#   - calculates bounding box
#   - draws the farm
#   - saves farm.json
# ============================================================


OUTPUT_DIR = os.path.join("data", "processed", "farm")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "farm.json")
MAP_FILE = os.path.join(OUTPUT_DIR, "farm_boundary.png")

GEOD = Geod(ellps="WGS84")


def parse_coordinate(value: str) -> float:
    """Accept decimal or DMS coordinates."""
    value = value.strip()

    if not value:
        raise ValueError("Coordinate cannot be empty.")

    try:
        return float(value)
    except ValueError:
        pass

    normalized = (
        value.replace("°", " ")
        .replace("'", " ")
        .replace('"', " ")
        .replace("d", " ")
        .replace("m", " ")
        .replace("s", " ")
    )
    normalized = re.sub(r"\s+", " ", normalized).strip()

    pattern = re.compile(
        r"^\s*(-?\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)\s+"
        r"(\d+(?:\.\d+)?)\s*"
        r"([NSEW])?\s*$",
        re.IGNORECASE,
    )

    match = pattern.match(normalized)
    if not match:
        raise ValueError("Invalid coordinate format.")

    degrees = float(match.group(1))
    minutes = float(match.group(2))
    seconds = float(match.group(3))
    direction = match.group(4)

    if minutes >= 60:
        raise ValueError("Minutes must be less than 60.")
    if seconds >= 60:
        raise ValueError("Seconds must be less than 60.")

    decimal = abs(degrees) + minutes / 60 + seconds / 3600

    if direction:
        direction = direction.upper()
        if direction in {"S", "W"}:
            decimal = -decimal
    elif degrees < 0:
        decimal = -decimal

    return decimal


def create_polygon(points):
    coords = [(lon, lat) for lat, lon in points]
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def geodesic_metrics(points):
    lons = [lon for lat, lon in points]
    lats = [lat for lat, lon in points]

    area_m2, perimeter_m = GEOD.polygon_area_perimeter(lons, lats)
    area_m2 = abs(area_m2)

    return {
        "square_meters": area_m2,
        "hectares": area_m2 / 10000.0,
        "acres": area_m2 / 4046.8564224,
        "perimeter_meters": perimeter_m,
        "perimeter_km": perimeter_m / 1000.0,
    }


def draw_farm(points, polygon):
    lons = [lon for lat, lon in points]
    lats = [lat for lat, lon in points]

    plot_lons = lons + [lons[0]]
    plot_lats = lats + [lats[0]]

    centroid = polygon.centroid

    plt.figure(figsize=(10, 8))
    plt.plot(plot_lons, plot_lats, marker="o")
    plt.fill(plot_lons, plot_lats, alpha=0.25)

    for i, (lat, lon) in enumerate(points, start=1):
        plt.annotate(
            f"P{i}",
            (lon, lat),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=10,
            fontweight="bold",
        )

    plt.scatter(centroid.x, centroid.y, marker="x", s=100)
    plt.annotate(
        "Centroid",
        (centroid.x, centroid.y),
        xytext=(8, -15),
        textcoords="offset points",
    )

    plt.title("AgriShield - Registered Farm Boundary")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.grid(alpha=0.3)
    plt.axis("equal")
    plt.tight_layout()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    plt.savefig(MAP_FILE, dpi=200, bbox_inches="tight")
    plt.show()


def save_farm(farm_id, points, polygon, metrics):
    coords = [[lon, lat] for lat, lon in points]
    if coords[0] != coords[-1]:
        coords.append(coords[0])

    centroid_lat = polygon.centroid.y
    centroid_lon = polygon.centroid.x

    lons = [p[1] for p in points]
    lats = [p[0] for p in points]

    farm_data = {
        "farm_id": farm_id,
        "point_count": len(points),
        "points": [
            {
                "id": f"P{i}",
                "latitude": lat,
                "longitude": lon,
            }
            for i, (lat, lon) in enumerate(points, start=1)
        ],
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords],
        },
        "area": {
            "square_meters": metrics["square_meters"],
            "hectares": metrics["hectares"],
            "acres": metrics["acres"],
        },
        "perimeter": {
            "meters": metrics["perimeter_meters"],
            "kilometers": metrics["perimeter_km"],
        },
        "centroid": {
            "latitude": centroid_lat,
            "longitude": centroid_lon,
        },
        "bounding_box": {
            "min_longitude": min(lons),
            "min_latitude": min(lats),
            "max_longitude": max(lons),
            "max_latitude": max(lats),
        },
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(farm_data, f, indent=4)

    return farm_data


def main():
    print("\n" + "=" * 65)
    print("             AGRISHIELD FARM REGISTRATION")
    print("=" * 65)
    print("\nEnter boundary points in order around the farm.")
    print("Use 'done' when finished. Minimum 3 points.\n")
    print("Coordinate formats supported:")
    print("  Decimal: 23.0748056")
    print('  DMS    : 23°04\'29.3"')

    points = []
    point_number = 1

    while True:
        print("\n" + "-" * 50)
        print(f"Enter boundary point P{point_number}")

        lat_input = input("Latitude (or done): ").strip()
        if lat_input.lower() == "done":
            break

        lon_input = input("Longitude: ").strip()

        try:
            lat = parse_coordinate(lat_input)
            lon = parse_coordinate(lon_input)

            if not -90 <= lat <= 90:
                raise ValueError("Latitude must be between -90 and 90.")
            if not -180 <= lon <= 180:
                raise ValueError("Longitude must be between -180 and 180.")

            points.append((lat, lon))
            print(f"✓ P{point_number} added: {lat:.10f}, {lon:.10f}")
            point_number += 1

        except ValueError as error:
            print(f"❌ {error}")
            print("Please enter the point again.")

    if len(points) < 3:
        print("\n❌ A farm polygon requires at least 3 points.")
        return

    polygon = create_polygon(points)

    if not polygon.is_valid:
        print("\n❌ Invalid polygon. Boundary points may cross.")
        return

    if polygon.area == 0:
        print("\n❌ Farm area is zero.")
        return

    farm_id = input("\nEnter Farm ID (default FARM_001): ").strip()
    farm_id = farm_id or "FARM_001"

    metrics = geodesic_metrics(points)
    farm_data = save_farm(
        farm_id,
        points,
        polygon,
        metrics,
    )

    draw_farm(points, polygon)

    print("\n" + "=" * 65)
    print("                 FARM REGISTERED")
    print("=" * 65)
    print(f"\nFarm ID       : {farm_id}")
    print(f"Boundary pts  : {len(points)}")
    print(f"Area          : {metrics['square_meters']:,.2f} m²")
    print(f"Area          : {metrics['hectares']:.4f} ha")
    print(f"Area          : {metrics['acres']:.4f} acres")
    print(f"Perimeter     : {metrics['perimeter_meters']:.2f} m")
    print(f"Perimeter     : {metrics['perimeter_km']:.4f} km")
    print(
        f"Centroid      : {farm_data['centroid']['latitude']:.8f}, "
        f"{farm_data['centroid']['longitude']:.8f}"
    )
    print(f"\nSaved farm   : {OUTPUT_FILE}")
    print(f"Saved map    : {MAP_FILE}")
    print("\n✓ Farm registration complete.")


if __name__ == "__main__":
    main()
