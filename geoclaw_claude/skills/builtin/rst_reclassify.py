"""
rst_reclassify.py — 栅格重分类 & 栅格计算 Skill
"""
# Copyright (c) 2025 UrbanComp Lab (https://urbancomp.net) — MIT License

SKILL_META = {
    "name":        "rst_reclassify",
    "version":     "1.0.0",
    "author":      "GeoClaw-claude Team",
    "description": "栅格重分类与运算：将栅格像元值按分级区间映射为新值，或执行多波段数学表达式计算（如 NDVI）",
    "category":    "raster",
    "inputs": [
        {"name": "raster_path", "type": "str", "desc": "输入栅格文件路径"},
        {"name": "mode",        "type": "str", "desc": "模式: reclass（重分类）/ calc（栅格计算）", "default": "reclass"},
        {"name": "breaks",      "type": "str", "desc": "重分类断点（逗号分隔，含边界）如 0,10,20,50,100", "default": ""},
        {"name": "values",      "type": "str", "desc": "各区间对应新值（逗号分隔，数量=断点数-1）",     "default": ""},
        {"name": "expression",  "type": "str", "desc": "栅格计算表达式，用 b1,b2 代指波段，如 (b1-b2)/(b1+b2)", "default": ""},
        {"name": "output_path", "type": "str", "desc": "输出栅格保存路径（.tif）", "default": ""},
    ],
    "outputs": [
        {"name": "result", "type": "RasterLayer", "desc": "输出栅格"},
        {"name": "report", "type": "str",          "desc": "像元值统计摘要"},
    ],
}


def run(ctx):
    import numpy as np
    from geoclaw_claude.analysis.raster_ops import load_raster, reclassify, raster_calc, save_raster

    raster_path = str(ctx.param("raster_path", ""))
    mode        = str(ctx.param("mode", "reclass")).lower()
    output_path = str(ctx.param("output_path", "")).strip()

    if not raster_path:
        raise ValueError("请提供 raster_path 参数")

    print(f"  加载栅格: {raster_path}")
    raster = load_raster(raster_path)

    if mode == "reclass":
        breaks_str = str(ctx.param("breaks", ""))
        values_str = str(ctx.param("values", ""))
        if not breaks_str or not values_str:
            raise ValueError("重分类模式需要提供 breaks 和 values 参数")
        breaks = [float(x.strip()) for x in breaks_str.split(",")]
        new_vals = [float(x.strip()) for x in values_str.split(",")]
        mapping = list(zip(zip(breaks[:-1], breaks[1:]), new_vals))
        result = reclassify(raster, mapping)
        op_zh = "重分类"

    elif mode == "calc":
        expression = str(ctx.param("expression", ""))
        if not expression:
            raise ValueError("栅格计算模式需要提供 expression 参数，如 (b1-b2)/(b1+b2)")
        result = raster_calc(raster, expression)
        op_zh = f"栅格计算 [{expression}]"
    else:
        raise ValueError(f"不支持的模式: {mode}，请选择 reclass 或 calc")

    # 统计输出结果
    data = result.data[0]
    valid = data[~np.isnan(data)]
    report = (
        f"栅格{op_zh}结果\n"
        f"  输入栅格  : {raster_path}\n"
        f"  模式      : {mode}\n"
        f"  输出形状  : {result.data.shape}\n"
        f"  值域      : {float(np.nanmin(valid)):.4f} ~ {float(np.nanmax(valid)):.4f}\n"
        f"  均值      : {float(np.nanmean(valid)):.4f}\n"
        f"  标准差    : {float(np.nanstd(valid)):.4f}"
    )
    print(report)

    if output_path:
        save_raster(result, output_path)
        print(f"  已保存至: {output_path}")
        report += f"\n  已保存至: {output_path}"

    return ctx.result(result=result, report=report)
