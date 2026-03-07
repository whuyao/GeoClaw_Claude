# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License
"""
geoclaw_claude.analysis.mobility
==================================
人类移动性数据分析模块（基于 trackintel）

数据层级:
  positionfixes → staypoints → triplegs → trips → locations

快速开始::

    from geoclaw_claude.analysis.mobility import (
        read_positionfixes, generate_full_hierarchy,
        mobility_summary, plot_mobility_layers
    )

    # 读入 GPS 数据
    pfs = read_positionfixes("gps_tracks.csv")

    # 一键生成完整层级
    h = generate_full_hierarchy(pfs)

    # 查看指标摘要
    print(mobility_summary(h))

    # 制图
    plot_mobility_layers(h, save_path="mobility_map.png")
"""

from geoclaw_claude.analysis.mobility.core import (
    read_positionfixes,
    read_positionfixes_csv,
    generate_staypoints,
    generate_triplegs,
    generate_trips,
    generate_locations,
    generate_full_hierarchy,
    predict_transport_mode,
    label_activity_staypoints,
)

from geoclaw_claude.analysis.mobility.metrics import (
    radius_of_gyration,
    jump_lengths,
    modal_split,
    tracking_quality,
    mobility_summary,
    identify_home_work,
)

from geoclaw_claude.analysis.mobility.visualization import (
    plot_mobility_layers,
    plot_modal_split,
    plot_activity_heatmap,
    plot_mobility_metrics,
    COLORS as MOBILITY_COLORS,
)

__all__ = [
    # 数据读入
    "read_positionfixes",
    "read_positionfixes_csv",
    # 层级生成
    "generate_staypoints",
    "generate_triplegs",
    "generate_trips",
    "generate_locations",
    "generate_full_hierarchy",
    # 语义标注
    "predict_transport_mode",
    "label_activity_staypoints",
    "identify_home_work",
    # 指标计算
    "radius_of_gyration",
    "jump_lengths",
    "modal_split",
    "tracking_quality",
    "mobility_summary",
    # 可视化
    "plot_mobility_layers",
    "plot_modal_split",
    "plot_activity_heatmap",
    "plot_mobility_metrics",
    "MOBILITY_COLORS",
]
