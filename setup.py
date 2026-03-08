"""
GeoClaw-claude 安装配置
UrbanComp Lab (https://urbancomp.net)
支持: pip install . 或 pip install -e .（开发模式）
安装后可用命令: geoclaw-claude
"""

from setuptools import setup, find_packages
from pathlib import Path

long_desc = (Path(__file__).parent / "README.md").read_text(encoding="utf-8") \
    if (Path(__file__).parent / "README.md").exists() else ""

setup(
    name="geoclaw-claude",
    version="2.4.0",
    description="Python GIS 工具集 — 空间分析 · 路网 · 栅格 · AI Skill",
    long_description=long_desc,
    long_description_content_type="text/markdown",
    author="UrbanComp Lab",
    author_email="contact@urbancomp.net",
    url="https://urbancomp.net",
    python_requires=">=3.9",
    packages=find_packages(exclude=["tests*", "examples*"]),
    include_package_data=True,
    package_data={"geoclaw_claude": ["skills/builtin/*.py"]},
    install_requires=[
        "geopandas>=0.14", "shapely>=2.0", "pyproj>=3.5",
        "numpy>=1.24", "pandas>=2.0", "matplotlib>=3.7",
        "click>=8.0", "requests>=2.28",
    ],
    extras_require={
        "full": ["folium>=0.14", "contextily>=1.3", "mapclassify>=2.6",
                 "rasterio>=1.3", "scipy>=1.10", "osmnx>=1.7", "anthropic>=0.25"],
        "dev":  ["pytest>=7.0", "black", "isort"],
    },
    entry_points={"console_scripts": ["geoclaw-claude=geoclaw_claude.cli:main"]},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Topic :: Scientific/Engineering :: GIS",
    ],
)
