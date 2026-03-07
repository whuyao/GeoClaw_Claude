"""
GeoClaw Wuhan Case Study
========================
Complete spatial analysis workflow using OpenStreetMap data:

1. Load pre-downloaded Wuhan OSM layers
2. Hospital service area analysis (1km, 3km, 5km)
3. Metro station density heatmap
4. Multi-layer city overview map
5. Choropleth: hospital distribution
6. Interactive web map
7. Export results

Usage:
    python3 examples/wuhan_analysis.py
"""
import sys, os
sys.path.insert(0, '/home/claude')
os.makedirs("/mnt/user-data/outputs/geoclaw_claude/wuhan", exist_ok=True)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import geopandas as gpd
import numpy as np

from geoclaw_claude.core.project import GeoClawProject
from geoclaw_claude.io.osm import load_wuhan_data
from geoclaw_claude.analysis.spatial_ops import buffer, calculate_area, nearest_neighbor
from geoclaw_claude.analysis.network import service_area_buffers, point_density
from geoclaw_claude.cartography.map_composer import MapComposer
from geoclaw_claude.cartography.renderer import InteractiveMap

OUTPUT = "/mnt/user-data/outputs/geoclaw_claude/wuhan"
DATA   = "/home/claude/geoclaw_claude/data/wuhan"

print("=" * 60)
print("  GeoClaw Wuhan Spatial Analysis")
print("=" * 60)

# ── 1. Load data ──────────────────────────────────────────────────────────────
print("\n[1] Loading OSM data layers...")
proj = GeoClawProject("Wuhan Urban Analysis", output_dir=OUTPUT)
layers = load_wuhan_data(DATA)
for name, layer in layers.items():
    proj.add_layer(layer, name=name)
print(proj.summary())

boundary   = layers["boundary"]
hospitals  = layers["hospitals"]
unis       = layers["universities"]
parks      = layers["parks"]
metro      = layers["metro_stations"]
roads      = layers["roads_main"]
water      = layers["water"]

# Clean: filter hospitals with names
hosp_named = hospitals.filter_by_attribute("name", "", "!=")
print(f"\n  Named hospitals: {len(hosp_named)}/{len(hospitals)}")

# ── 2. Hospital Service Area Analysis ─────────────────────────────────────────
print("\n[2] Hospital service area analysis...")
service_areas = service_area_buffers(hosp_named, distances_km=[1, 3, 5])
proj.add_layer(service_areas, "hospital_service_areas")
print(f"  Service area rings: {len(service_areas)} features")

# ── 3. Nearest hospital distance ─────────────────────────────────────────────
print("\n[3] Nearest hospital analysis...")
metro_to_hosp = nearest_neighbor(metro, hosp_named)
metro_to_hosp_data = metro_to_hosp.data.copy()
mean_dist = metro_to_hosp_data["nn_distance"].mean()
max_dist  = metro_to_hosp_data["nn_distance"].max()
print(f"  Mean distance (metro → hospital): {mean_dist:.0f}m")
print(f"  Max distance (metro → hospital):  {max_dist:.0f}m")

# ── 4. Map 1: City Overview (urban dark theme) ───────────────────────────────
print("\n[4] Rendering: City Overview Map...")
composer1 = MapComposer(
    figsize=(16, 13), dpi=150, palette="urban",
    title="武汉市城区概览  |  Wuhan Urban Overview",
    subtitle="数据来源: OpenStreetMap  |  GeoClaw v0.1"
)
composer1.add_layer(boundary, role="boundary", alpha=0.15, linewidth=1.5,
                    color="#3a3a5c", edge_color="#5a5a8c", zorder=1, label="城市边界")
composer1.add_layer(water,    role="water",    alpha=0.6,  markersize=2,  zorder=2, label="水体")
composer1.add_layer(parks,    role="park",     alpha=0.5,  markersize=3,  zorder=3, label="公园绿地")
composer1.add_layer(roads,    role="road",     alpha=0.5,  linewidth=0.6, zorder=4, label="主干道")
composer1.add_layer(metro,    role="metro",    alpha=0.8,  markersize=3,  zorder=5, label="地铁站点")
composer1.add_layer(hosp_named, role="hospital", alpha=0.9, markersize=6, zorder=6, label="医院")
composer1.render(f"{OUTPUT}/01_wuhan_overview_urban.png")

# ── 5. Map 2: Hospital Service Coverage (light theme) ────────────────────────
print("\n[5] Rendering: Hospital Service Coverage Map...")

# Build concentric rings manually for visualization
from geoclaw_claude.analysis.network import service_area_buffers
rings_1km = service_area_buffers(hosp_named, distances_km=[1])
rings_3km = service_area_buffers(hosp_named, distances_km=[3])
rings_5km = service_area_buffers(hosp_named, distances_km=[5])
proj.add_layer(rings_5km, "coverage_5km")
proj.add_layer(rings_3km, "coverage_3km")
proj.add_layer(rings_1km, "coverage_1km")

composer2 = MapComposer(
    figsize=(14, 11), dpi=150, palette="light",
    title="武汉市医院服务覆盖范围  |  Hospital Service Coverage",
    subtitle="1km / 3km / 5km 服务圈  |  GeoClaw v0.1"
)
composer2.add_layer(boundary, role="boundary", alpha=0.08, color="#e8e0d8", edge_color="#aaaaaa", zorder=1, label="城市边界")
composer2.add_layer(rings_5km, color="#ff8a65", alpha=0.12, edge_color="#ff5722", linewidth=0.3, zorder=2, label="5km 服务圈")
composer2.add_layer(rings_3km, color="#ef5350", alpha=0.18, edge_color="#c62828", linewidth=0.3, zorder=3, label="3km 服务圈")
composer2.add_layer(rings_1km, color="#b71c1c", alpha=0.25, edge_color="#880000", linewidth=0.3, zorder=4, label="1km 服务圈")
composer2.add_layer(roads,     role="road",     alpha=0.3, linewidth=0.5, color="#d7b896", zorder=5, label="主干道")
composer2.add_layer(hosp_named, role="hospital", alpha=1.0, markersize=5, zorder=6, label=f"医院 (n={len(hosp_named)})")
composer2.render(f"{OUTPUT}/02_hospital_coverage.png")

# ── 6. Map 3: Metro & University Distribution (blueprint) ────────────────────
print("\n[6] Rendering: Metro & University Distribution Map...")
composer3 = MapComposer(
    figsize=(14, 11), dpi=150, palette="blueprint",
    title="武汉市轨道交通与高校分布  |  Metro & Universities",
    subtitle="地铁站点 & 高校位置  |  GeoClaw v0.1"
)
composer3.add_layer(boundary, role="boundary", alpha=0.1, color="#1a3a5c", edge_color="#2d5f8a", zorder=1, label="城市边界")
composer3.add_layer(water,    role="water",    alpha=0.5, markersize=2, zorder=2, label="水体")
composer3.add_layer(roads,    role="road",     alpha=0.3, linewidth=0.5, color="#90caf9", zorder=3, label="主干道")
composer3.add_layer(metro,    role="metro",    alpha=0.7, markersize=3, zorder=4, label=f"地铁站 (n={len(metro)})")
composer3.add_layer(unis,     role="university", alpha=1.0, markersize=8, marker="^", zorder=5, label=f"高校 (n={len(unis)})")
composer3.render(f"{OUTPUT}/03_metro_university.png")

# ── 7. Map 4: KDE Density Heatmap ─────────────────────────────────────────────
print("\n[7] Rendering: Hospital KDE Density Map...")
wuhan_bounds = boundary.bounds
density = point_density(
    hosp_named,
    resolution=0.005,
    bandwidth=0.04,
    bounds=(wuhan_bounds[0]-0.1, wuhan_bounds[1]-0.1,
            wuhan_bounds[2]+0.1, wuhan_bounds[3]+0.1)
)

composer4 = MapComposer(
    figsize=(14, 11), dpi=150, palette="urban",
    title="武汉市医疗资源密度分布  |  Hospital Density (KDE)",
    subtitle="核密度估计 Kernel Density Estimation  |  GeoClaw v0.1"
)
composer4.add_kde_heatmap(density, cmap="hot", alpha=0.65, zorder=2)
composer4.add_layer(boundary, color="none", edge_color="#88aaff", alpha=0.6, linewidth=1.5, zorder=3, label="城市边界")
composer4.add_layer(roads, role="road", alpha=0.2, linewidth=0.4, color="#ffffff", zorder=4, label="主干道")
composer4.add_layer(hosp_named, role="hospital", alpha=0.8, markersize=3, zorder=5, label="医院")
composer4.render(f"{OUTPUT}/04_hospital_kde.png")

# ── 8. Interactive Map ────────────────────────────────────────────────────────
print("\n[8] Building interactive web map...")
imap = InteractiveMap(basemap="light", zoom=10)
imap.set_center(30.57, 114.30)
imap.add_layer(rings_5km, color="#ff8a65", fill_opacity=0.08, weight=1)
imap.add_layer(rings_3km, color="#ef5350", fill_opacity=0.12, weight=1)
imap.add_layer(rings_1km, color="#b71c1c", fill_opacity=0.18, weight=1)
imap.add_layer(roads,    color="#888888", fill_opacity=0, weight=1.0)
imap.add_layer(metro,    color="#ff6f00", popup_cols=["name"], cluster_points=True)
imap.add_layer(hosp_named, color="#e53935", popup_cols=["name", "beds", "operator"])
imap.add_layer(unis,     color="#7b1fa2", popup_cols=["name"])
imap.save(f"{OUTPUT}/05_interactive_map.html")

# ── 9. Statistics Report ──────────────────────────────────────────────────────
print("\n[9] Analysis Report:")
print("─" * 50)
print(f"  City area bbox  : {boundary.bounds}")
print(f"  Hospitals       : {len(hospitals)} total | {len(hosp_named)} named")
print(f"  Universities    : {len(unis)}")
print(f"  Parks           : {len(parks)}")
print(f"  Metro stops     : {len(metro)}")
print(f"  Main roads      : {len(roads)} segments")
print(f"  Water features  : {len(water)}")
print(f"  Mean hosp→metro : {mean_dist:.0f}m")

# Top hospitals by name length (proxy for completeness)
top_hosp = hosp_named.data[hosp_named.data["name"].str.len() > 4][["name","operator"]].head(10)
print("\n  Sample hospitals:")
print(top_hosp.to_string(index=False))

print("\n" + "=" * 60)
print("  All outputs saved to:", OUTPUT)
print("=" * 60)
