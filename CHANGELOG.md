# GeoClaw-claude 版本历史

**UrbanComp Lab** (https://urbancomp.net)

---

## v1.0.0 (2025-03)

**首个正式发布版本。**

### 新增功能
- **CLI 命令行工具** (`geoclaw-claude`)
  - `onboard` — 交互式初始化向导，引导配置 API Key、数据目录、网络参数
  - `config show/get/set` — 配置项查看与修改
  - `skill list/run/install/new` — Skill 生命周期管理
  - `download osm/url` — 命令行数据下载
  - `test` — 环境验证
- **配置系统** (`config.py`)
  - 统一配置文件 `~/.geoclaw_claude/config.json`
  - 支持环境变量覆盖（`GEOCLAW_<KEY>=value`）
- **Skill 系统** (`skill_manager.py`)
  - 用户自定义分析脚本规范（`SKILL_META` + `run(ctx)`）
  - `SkillContext` 提供图层访问、参数读取、AI调用、结果保存接口
  - 内置 Skill：`hospital_coverage`（医院覆盖分析 + AI 解读）
- **远程数据下载** (`io/remote.py`)
  - HTTP/HTTPS 文件下载（含缓存机制）
  - WFS 标准接口支持
  - 天地图 POI API 接入
- **路网分析完善** (`analysis/network.py`)
  - `build_network()` — 从地名/bbox/GeoLayer 构建路网
  - `shortest_path()` — Dijkstra 最短路径（距离/时间权重）
  - `isochrone()` — N 分钟等时圈多边形
  - `service_areas()` — 批量设施服务区分析
  - `network_stats()` — 路网密度/连通性/迂回度统计
- **栅格空间分析** (`analysis/raster_ops.py`)
  - `RasterLayer` 栅格数据容器
  - `slope()` / `aspect()` / `hillshade()` — DEM 地形分析
  - `reclassify()` — 栅格重分类
  - `raster_calc()` — 栅格计算器（numpy 表达式）
  - `zonal_stats()` — 矢量分区统计
  - `clip_raster()` / `resample()` — 裁剪与重采样
- **坐标转换工具** (`utils/coord_transform.py`)
  - WGS84 ↔ GCJ-02 ↔ BD-09 三坐标系完整互转
  - `transform_layer()` 支持整个 GeoLayer 批量转换
- **安装支持**
  - `install.sh` 一键安装脚本（`--dev` / `--mini` 模式）
  - `setup.py` 支持 `pip install -e .`
  - 命令注册 `geoclaw-claude` 入口点

### 改进
- 全面重命名：`geoclaw` → `geoclaw_claude`，避免与实验室其他项目冲突
- 所有模块统一添加 UrbanComp Lab 版权声明
- `__init__.py` 加入完整版本历史追踪

---

## v0.2.0 (2025-02)

### 新增
- CLI 骨架（click）
- Skill 系统原型
- 远程数据下载基础框架
- 路网分析模块骨架（`network.py`）

### 改进
- 模块重命名为 `geoclaw_claude`

---

## v0.1.0 (2025-01)

**初始版本（内部使用）。**

### 功能
- `GeoLayer` 核心图层类
- `GeoClawProject` 项目管理
- OSM/Overpass 数据下载 (`io/osm.py`)
- 空间分析：缓冲区、叠加、最近邻、KDE (`analysis/spatial_ops.py`)
- 静态制图与交互地图 (`cartography/`)
- GeoJSON/Shapefile/CSV 读写 (`io/vector.py`)
- 武汉城市分析示例 (`examples/wuhan_analysis.py`)

---

*GeoClaw-claude 由 UrbanComp Lab (https://urbancomp.net) 开发维护，MIT 许可证开放使用。*
