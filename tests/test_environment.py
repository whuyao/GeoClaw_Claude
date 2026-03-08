"""
GeoClaw Environment & Smoke Tests
Run this to verify all modules load and core operations work.
"""
import sys
import traceback
from pathlib import Path

# Add geoclaw_claude to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PASS, FAIL, WARN = "✓", "✗", "⚠"
results = []

def _run(name, fn):
    try:
        fn()
        print(f"  {PASS} {name}")
        results.append((name, True, None))
    except Exception as e:
        print(f"  {FAIL} {name}: {e}")
        results.append((name, False, str(e)))


print("\n" + "=" * 60)
print("  GeoClaw Environment Test Suite")
print("=" * 60)

# ─── 1. Library imports ───────────────────────────────────────────────────────
print("\n[1] Library Imports")
_run("geopandas", lambda: __import__("geopandas"))
_run("shapely", lambda: __import__("shapely"))
_run("pyproj", lambda: __import__("pyproj"))
_run("numpy", lambda: __import__("numpy"))
_run("pandas", lambda: __import__("pandas"))
_run("matplotlib", lambda: __import__("matplotlib"))
_run("folium", lambda: __import__("folium"))
_run("rasterio", lambda: __import__("rasterio"))
_run("scipy", lambda: __import__("scipy"))
_run("networkx", lambda: __import__("networkx"))

# ─── 2. GeoClaw module imports ────────────────────────────────────────────────
print("\n[2] GeoClaw Modules")
_run("geoclaw_claude.__init__", lambda: __import__("geoclaw_claude"))
_run("geoclaw_claude.core.layer", lambda: __import__("geoclaw_claude.core.layer"))
_run("geoclaw_claude.core.project", lambda: __import__("geoclaw_claude.core.project"))
_run("geoclaw_claude.io.vector", lambda: __import__("geoclaw_claude.io.vector"))
_run("geoclaw_claude.analysis.spatial_ops", lambda: __import__("geoclaw_claude.analysis.spatial_ops"))
_run("geoclaw_claude.cartography.renderer", lambda: __import__("geoclaw_claude.cartography.renderer"))

# ─── 3. Core functionality ────────────────────────────────────────────────────
print("\n[3] Core GeoLayer")
import geopandas as gpd
from shapely.geometry import Point, Polygon
from geoclaw_claude.core.layer import GeoLayer
from geoclaw_claude.core.project import GeoClawProject

def make_sample_layer():
    gdf = gpd.GeoDataFrame({
        "name":  ["Beijing", "Shanghai", "Guangzhou", "Chengdu", "Wuhan"],
        "pop_m": [21.5, 24.8, 13.9, 16.3, 11.2],
        "geometry": [Point(116.4, 39.9), Point(121.5, 31.2),
                     Point(113.3, 23.1), Point(104.1, 30.6), Point(114.3, 30.6)],
    }, crs="EPSG:4326")
    return gdf

def t_layer_create():
    gdf = make_sample_layer()
    layer = GeoLayer(gdf, name="China Cities")
    assert len(layer) == 5
    assert layer.epsg == 4326

def t_layer_filter():
    gdf = make_sample_layer()
    layer = GeoLayer(gdf, name="China Cities")
    filtered = layer.filter_by_attribute("pop_m", 15, ">")
    assert len(filtered) == 3

def t_layer_reproject():
    gdf = make_sample_layer()
    layer = GeoLayer(gdf, name="China Cities")
    utm = layer.reproject("EPSG:32650")
    assert utm.epsg == 32650

def t_project():
    proj = GeoClawProject("Test Project")
    gdf = make_sample_layer()
    proj.add_geodataframe(gdf, "China Cities")
    assert "China Cities" in proj.list_layers()

_run("GeoLayer creation", t_layer_create)
_run("GeoLayer filter", t_layer_filter)
_run("GeoLayer reproject", t_layer_reproject)
_run("GeoClawProject", t_project)

# ─── 4. Spatial analysis ─────────────────────────────────────────────────────
print("\n[4] Spatial Analysis")
from geoclaw_claude.analysis.spatial_ops import buffer, nearest_neighbor, calculate_area

def t_buffer():
    gdf = make_sample_layer()
    layer = GeoLayer(gdf, name="Cities")
    buf = buffer(layer, 50000, unit="meters")
    assert buf.geometry_type == "Polygon"
    assert len(buf) == 5

def t_area():
    # Create polygon layer for area calculation
    poly_gdf = gpd.GeoDataFrame({
        "name": ["Zone A"],
        "geometry": [Polygon([(100,20),(110,20),(110,30),(100,30),(100,20)])]
    }, crs="EPSG:4326")
    poly_layer = GeoLayer(poly_gdf, name="Zones")
    result = calculate_area(poly_layer, column="area_km2", unit="km2")
    assert "area_km2" in result.data.columns

def t_nearest():
    gdf = make_sample_layer()
    layer = GeoLayer(gdf, name="Cities")
    result = nearest_neighbor(layer, layer)
    assert "nn_distance" in result.data.columns

_run("Buffer (50km)", t_buffer)
_run("Calculate area", t_area)
_run("Nearest neighbor", t_nearest)

# ─── 5. Cartography ──────────────────────────────────────────────────────────
print("\n[5] Cartography")
from geoclaw_claude.cartography.renderer import StaticMap, InteractiveMap
import os, tempfile

def t_static_map():
    gdf = make_sample_layer()
    layer = GeoLayer(gdf, name="Cities")
    m = StaticMap(figsize=(6, 4), dpi=72)
    m.add_layer(layer, color="red")
    m.set_title("Test Map")
    m.render()
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        m.save(f.name)
        assert os.path.exists(f.name)
        os.unlink(f.name)

def t_interactive_map():
    gdf = make_sample_layer()
    layer = GeoLayer(gdf, name="Cities")
    m = InteractiveMap()
    m.add_layer(layer)
    result = m.build()
    assert result is not None

_run("Static map (PNG)", t_static_map)
_run("Interactive map (Folium)", t_interactive_map)

# ─── Summary ──────────────────────────────────────────────────────────────────
passed = sum(1 for _, ok, _ in results if ok)
total = len(results)
failed = [(n, e) for n, ok, e in results if not ok]

print(f"\n{'=' * 60}")
print(f"  Results: {passed}/{total} passed", end="")
if failed:
    print(f" | {len(failed)} FAILED:")
    for name, err in failed:
        print(f"    {FAIL} {name}: {err}")
else:
    print(" 🎉")
print("=" * 60 + "\n")
