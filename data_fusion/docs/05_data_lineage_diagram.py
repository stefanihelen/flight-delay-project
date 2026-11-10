# -*- coding: utf-8 -*-
"""
05_data_lineage_diagram.py
成员2 补充交付：美国航班延误多源数据关联图 / 血缘图

阅读层级（自上而下）：
  四个独立来源 -> Raw(data/raw) -> 清洗步骤(cleaning/*.py) -> Cleaned(data/cleaned)
  -> 融合步骤(04_fusion_weather.py) -> Integrated(data/integrated) -> 质量检查

输出（与本脚本同目录 docs/）：
  05_data_lineage_diagram.png   高分辨率位图（>=200dpi，宽>=2400px）
  05_data_lineage_diagram.pdf   矢量版，可直接查看/再编辑
  05_data_lineage_diagram.svg   矢量源文件，便于再编辑

运行（项目根目录）：
  python docs/05_data_lineage_diagram.py
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# ---------- 中文字体 ----------
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun"]
plt.rcParams["axes.unicode_minus"] = False

OUT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parent.parent

# ---------- 画布：坐标 0-100 x, 0-100 y ----------
FIG_W, FIG_H = 22.0, 15.0
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")

# 配色
C_SRC = ("#dbe9f7", "#2b6cb0")   # 来源
C_RAW = ("#eceff3", "#718096")   # Raw
C_CLR = ("#fef3c7", "#b7791f")   # 清洗脚本
C_META = ("#e9d8fd", "#6b46c1")  # metadata 接口表
C_CLD = ("#dcf5e5", "#2f855a")   # Cleaned 产物
C_FUS = ("#fed7e2", "#b83280")   # 融合
C_INT = ("#c6f6d5", "#22543d")   # Integrated
C_QC = ("#e2e8f0", "#4a5568")    # 质量检查


def box(x, y, w, h, face, edge, title, lines, title_fs=10.5, body_fs=8.6,
        title_color="#1a202c", pad=0.35):
    """以 (x,y) 为中心绘制圆角框，返回 (x,y,w,h) 几何。"""
    p = FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                       boxstyle="round,pad=0.18,rounding_size=0.5",
                       linewidth=1.4, facecolor=face, edgecolor=edge, zorder=2)
    ax.add_patch(p)
    tx = x - w / 2 + pad
    ty = y + h / 2 - pad - 0.15
    ax.text(tx, ty, title, fontsize=title_fs, fontweight="bold",
            color=title_color, va="top", ha="left", zorder=3)
    if lines:
        body = "\n".join(lines)
        ax.text(tx, ty - 1.05, body, fontsize=body_fs, color="#2d3748",
                va="top", ha="left", zorder=3, linespacing=1.35)
    return (x, y, w, h)


def arrow(p1, p2, label=None, color="#4a5568", style="-", lw=1.5,
          label_fs=8.0, label_dx=0.0, label_dy=0.0, connection="arc3,rad=0",
          label_bg=True):
    a = FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=13,
                        linewidth=lw, color=color, linestyle=style,
                        connectionstyle=connection, zorder=1)
    ax.add_patch(a)
    if label:
        mx = (p1[0] + p2[0]) / 2 + label_dx
        my = (p1[1] + p2[1]) / 2 + label_dy
        bbox = dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.85) if label_bg else None
        ax.text(mx, my, label, fontsize=label_fs, color=color, ha="center",
                va="center", zorder=4, bbox=bbox, fontweight="bold")


# ================= 标题 =================
ax.text(50, 98.3, "美国航班延误多源数据血缘图（成员2：清洗与融合）",
        fontsize=17, fontweight="bold", ha="center", va="center", color="#1a202c")
ax.text(50, 95.6, "处理路径：四个独立来源  →  Raw  →  Cleaned  →  Integrated　｜　关联维度：地点（机场代码/站点/坐标）＋ 时间（本地计划起飞→UTC）",
        fontsize=10.5, ha="center", va="center", color="#4a5568")

# ================= 第1层：四个独立来源 =================
y_src = 89.5
srcs = [
    (12.5, "S01 主要｜BTS 美国交通统计局",
     ["Reporting Carrier On-Time Performance (1987–present)",
      "2024 全年官方 PREZIP 月度 ZIP × 12",
      "关联字段：Origin/Dest·CRSDepTime·AirportID"]),
    (37.5, "S02 主要｜NOAA／NCEI Global Hourly (ISD)",
     ["2024 年逐站 CSV + isd-history.csv",
      "正式 346 站（SGU 试采集另存、不计入）",
      "关联字段：STATION·DATE（按 UTC 解释）"]),
    (62.5, "S03 辅助｜OurAirports 机场资料快照",
     ["airports.csv 快照 86,293 条（US 32,697）",
      "iata_code / ident / gps_code / 经纬度",
      "Public Domain；不保证实时性"]),
    (87.5, "S04 辅助｜U.S. Census Bureau 州界",
     ["cb_2024_us_state_500k.zip（1:500,000）",
      "56 个州及州级等同地区 Polygon",
      "PRJ：NAD83 / GRS 1980"]),
]
src_boxes = []
for cx, t, ls in srcs:
    src_boxes.append(box(cx, y_src, 21.5, 7.2, C_SRC[0], C_SRC[1], t, ls))

# ================= 第2层：Raw =================
y_raw = 79.0
raws = [
    (12.5, "data/raw/BTS/",
     ["解压后 12 个月度 CSV", "原始 7,079,061 行 · 3.20 GB",
      "（外层年度 ZIP 为本地汇集，非官方年度产品）"]),
    (37.5, "data/raw/NOAA/2024/*.csv",
     ["正式 346 站逐文件 CSV", "4,529,560 条观测 · 2.52 GB",
      "含 SOD/SOM 等多报告类型原始记录"]),
    (62.5, "data/raw/OurAirports/airports.csv",
     ["86,293 行快照", "SHA-256 已存档（metadata/ourairports_inventory.json）"]),
    (87.5, "data/raw/Census/cb_2024_us_state_500k.zip",
     ["ZIP CRC 通过 · 56 条属性", "SHP / DBF / PRJ / SHX 齐备"]),
]
raw_boxes = []
for cx, t, ls in raws:
    raw_boxes.append(box(cx, y_raw, 21.5, 6.4, C_RAW[0], C_RAW[1], t, ls, body_fs=8.2))

for i in range(4):
    arrow((src_boxes[i][0], y_src - 3.6), (src_boxes[i][0], y_raw + 3.2),
          color=C_SRC[1], lw=1.3)

# ================= 第3层：清洗步骤 =================
y_clr = 66.5
c1 = box(12.5, y_clr, 21.5, 9.6, C_CLR[0], C_CLR[1],
         "01_clean_bts.py（--mode sample / full）",
         ["逐月读取 12 个月 CSV、统一字段口径",
          "标记 Cancelled=96,315 / Diverted=17,499",
          "到达缺失 97,854；ArrDel15 不一致 = 0",
          "仅 2024-08 剔除 1 行缺键（航班号缺失）"])
c2 = box(37.5, y_clr, 21.5, 9.6, C_CLR[0], C_CLR[1],
         "02_verify_sample.py → 02_clean_noaa.py full",
         ["先 LAX/ORD/JFK 样本逐条对 METAR 原文",
          "按 ISD 文档解析 温/露/压/风/能见/降水",
          "仅保留 FM-15 / FM-16，保留原始质量码",
          "VIS 码值直接=米（不 ×10）；precip 缺测≠无雨"])
c3 = box(62.5, y_clr, 21.5, 9.6, C_CLR[0], C_CLR[1],
         "03_airport_timezones.py",
         ["坐标优先级：mapping_reviewed → OurAirports 回退",
          "实际 348/348 全部来自 mapping_reviewed",
          "timezonefinder(lat,lon) → IANA 时区",
          "★ OurAirports 直接读坐标：未触发（潜在回退源）"])
c4 = box(87.5, y_clr, 21.5, 9.6, C_CLR[0], C_CLR[1],
         "03_state_check.py（空间核验）",
         ["解压 Census SHP → shapely STRtree 索引",
          "机场 Point 逐面 point-in-polygon",
          "州界 NAD83 vs 机场坐标 WGS84",
          "500k 比例尺下同按十进制度近似（未投影转换）"])

# raw -> cleaning
arrow((12.5, y_raw - 3.2), (12.5, y_clr + 4.8), color=C_RAW[1], lw=1.3)
arrow((37.5, y_raw - 3.2), (37.5, y_clr + 4.8), color=C_RAW[1], lw=1.3)
# OurAirports raw -> 03 timezones：虚线回退
arrow((62.5, y_raw - 3.2), (62.5, y_clr + 4.8), color="#a0aec0", style=(0, (4, 3)),
      lw=1.2, label="回退路径（348/348 未触发）", label_dy=1.6, label_fs=7.6)
# Census raw -> 03_state_check
arrow((87.5, y_raw - 3.2), (87.5, y_clr + 4.8), color=C_RAW[1], lw=1.3,
      label="cb SHP (NAD83)", label_dx=2.2, label_fs=7.6)

# 03_finalize 小框（在州界脚本下方）
cfin = box(87.5, 56.6, 21.5, 3.4, C_CLR[0], C_CLR[1],
           "03_finalize.py：时区/州界汇总 + 日志",
           ["→ airport_timezone_stats.json（金标准 5 机场全 PASS）"],
           title_fs=9.2, body_fs=7.8)
arrow((87.5, y_clr - 4.8), (87.5, 56.6 + 1.8), color=C_CLR[1], lw=1.2)
arrow((62.5, y_clr - 4.8), (80.5, 56.6 + 1.0), color=C_CLR[1], lw=1.0,
      connection="arc3,rad=-0.15")

# ================= metadata 接口表（成员1交付，供 03 与 04 使用） =================
meta = box(37.5, 55.6, 30.0, 4.6, C_META[0], C_META[1],
           "metadata/airport_station_mapping_reviewed.csv（成员1交付的 348 行修订映射）",
           ["airport_code ↔ station_id 映射 + 复核坐标（lat/lon）；含 PBI 别名核验、SGU 位置冲突、XWA 未匹配等例外",
            "键：airport_code / bts_airport_id；坐标经 OurAirports 身份核对后人工修订（上游追溯见 data_sources.md）"],
           title_fs=9.4, body_fs=7.8)
# meta -> timezone script (复核坐标)
arrow((52.0, 57.9), (60.0, y_clr - 4.4), color=C_META[1], lw=1.2,
      style=(0, (5, 3)), label="复核坐标 348/348", label_dx=3.2, label_dy=-0.6, label_fs=7.6)

# ================= 第4层：Cleaned 产物 =================
y_cld = 45.0
d1 = box(12.5, y_cld, 21.5, 8.4, C_CLD[0], C_CLD[1],
         "data/cleaned/bts_flights_2024.parquet",
         ["7,079,060 行 × 20 列（原始 7,079,061→-1）",
          "sched_dep_local：本地计划起飞时刻",
          "附 bts_cleaning_log.csv / bts_clean_stats.json"])
d2 = box(37.5, y_cld, 21.5, 8.4, C_CLD[0], C_CLD[1],
         "data/cleaned/noaa_obs_2024.parquet",
         ["3,905,968 行 × 19 列（4,529,560→-623,592）",
          "FM-15 3,204,352 / FM-16 701,616 · 346 站",
          "obs_utc + 各要素质量码；附 noaa_clean_stats.json"])
d3 = box(62.5, y_cld, 21.5, 8.4, C_CLD[0], C_CLD[1],
         "data/cleaned/airport_timezones.csv",
         ["348 机场 · 22 个唯一 IANA 时区",
          "coord_source=mapping_reviewed（348）",
          "tz_method=timezonefinder（348）"])
d4 = box(87.5, y_cld, 21.5, 8.4, C_CLD[0], C_CLD[1],
         "data/cleaned/airport_state_check.csv",
         ["state_consistent=1：345 机场",
          "na：3 个 TT 领地（GUM/PPG/SPN）",
          "polygon_state：机场落入的 Census 州面"])

arrow((12.5, y_clr - 4.8), (12.5, y_cld + 4.2), color=C_CLR[1], lw=1.4)
arrow((37.5, y_clr - 4.8), (37.5, y_cld + 4.2), color=C_CLR[1], lw=1.4)
arrow((62.5, y_clr - 4.8), (62.5, y_cld + 4.2), color=C_CLR[1], lw=1.4)
arrow((87.5, 56.6 - 1.8), (87.5, y_cld + 4.2), color=C_CLR[1], lw=1.2,
      label="州界核验结果", label_dx=2.6, label_fs=7.4)
# timezone -> state_check（坐标接力，走两列之间的窄缝）
arrow((73.4, y_cld + 0.6), (76.6, y_cld + 0.6), color=C_CLD[1], lw=1.1,
      label="坐标接力", label_fs=7.2, label_dy=1.5)

# ================= 第5层：融合步骤 =================
y_fus = 30.5
fus = box(50.0, y_fus, 88.0, 12.6, C_FUS[0], C_FUS[1],
          "04_fusion_weather.py —— 航班 × 天气融合（一行一班；读入全部 Cleaned 产物 + mapping_reviewed + 正式346站清单）",
          ["关联键① 地点：flights.origin(airport_code) ──map──▶ station_id（经 mapping_reviewed）；同时带入 origin_tz_iana、origin_polygon_state；XWA=无站、SGU=不在346清单",
           "关联键② 时间：sched_dep_local ──tz_localize(origin_tz_iana, ambiguous=False；含夏令时、CRSDepTime=2400 跨日按次日00:00)──▶ dep_utc（UTC）",
           "关联键③ 匹配：obs 先按 (station_id, obs_utc) 去重、同刻 FM-15 优先（3,905,968 → 3,898,753）；再 merge_asof(by=station_id, backward, obs_utc ≤ dep_utc)，窗口 ≤ 90 分钟",
           "空间核验：机场 lat·lon ∩ Census polygon → polygon_state；NAD83/WGS84 同按十进制度近似；输出 weather_gap_minutes 与 weather_match_within_60 标记"],
          title_fs=10.2, body_fs=8.6)

# cleaned -> fusion
arrow((12.5, y_cld - 4.2), (18.0, y_fus + 6.3), color=C_CLD[1], lw=1.5,
      label="bts_flights（左表）", label_dx=-2.5, label_dy=1.2, label_fs=7.8)
arrow((37.5, y_cld - 4.2), (40.0, y_fus + 6.3), color=C_CLD[1], lw=1.5,
      label="noaa_obs（右表）", label_dx=-1.5, label_dy=1.4, label_fs=7.8)
arrow((62.5, y_cld - 4.2), (58.0, y_fus + 6.3), color=C_CLD[1], lw=1.3,
      label="tz IANA", label_dx=1.8, label_dy=1.2, label_fs=7.6)
arrow((87.5, y_cld - 4.2), (82.0, y_fus + 6.3), color=C_CLD[1], lw=1.3,
      label="polygon_state", label_dx=3.2, label_dy=1.0, label_fs=7.6)
# metadata -> fusion：走 col1/col2 之间的竖缝，避免穿过任何产品框；标签放到两层空档
arrow((24.0, 55.6 - 2.3), (24.0, y_fus + 6.3), color=C_META[1], lw=1.3,
      style=(0, (5, 3)), label="airport_code↔station_id",
      label_dx=0.0, label_dy=-6.6, label_fs=7.4)

# ================= 第6层：Integrated =================
y_int = 16.5
inte = box(50.0, y_int, 88.0, 9.4, C_INT[0], C_INT[1],
           "data/integrated/flights_weather_2024.parquet —— 一行一班主表：7,079,060 行 × 44 列（flight_id 唯一；行数与 BTS 清洗表完全一致）",
           ["weather_match_status：matched 7,055,161（99.662%）｜ 60 分钟窗口 7,047,642（99.556%）｜ gap 中位 25 分钟",
            "陈旧观测 no_obs_within_90 18,904（>90min，中位约194min，建模前应过滤）｜ 无站 XWA 1,972 班 ｜ SGU 3,023 班 ｜ WYS 仅 2024-04-29~11-06 有观测，覆盖外自然未匹配、不补造天气",
            "附 data/integrated/fusion_stats.json（匹配率/gap分布/质量码分布/州界一致性）与 flights_weather_2024_sample.csv（前 2 万行，仅查看）"],
           title_fs=10.2, body_fs=8.6)
arrow((50.0, y_fus - 6.3), (50.0, y_int + 4.7), color=C_FUS[1], lw=1.8)

# ================= 第7层：质量检查 =================
y_qc = 5.6
qc = box(50.0, y_qc, 96.0, 6.6, C_QC[0], C_QC[1],
         "质量检查与证据（随图交付）",
         ["cleaning/logs/ 8 份核验日志：bts_sample_check / bts_final_check / noaa_sample_verify / noaa_format_notes / noaa_full_run / noaa_final_check / timezone_state_verify / fusion_check",
          "docs/quality_report.md（10 项口径）· docs/field_dictionary.md（5 张表逐列定义）· metadata/member2_deliverable_checksums.sha256（交付件 SHA-256）",
          "硬校验：flight_id 唯一 · 融合前后行数不变 7,079,060 · dep_utc NaT=0 · 州界 345 一致/3 TT 领地编码差异（非位置错误）"],
         title_fs=10.0, body_fs=8.2)
arrow((50.0, y_int - 4.7), (50.0, y_qc + 3.4), color=C_QC[1], lw=1.4)

# ================= 图例 =================
ax.text(2.0, 93.6, "图例：实线=实际数据流　虚线=回退/接口路径（未触发或仅映射）",
        fontsize=8.4, color="#4a5568", ha="left", va="center")

# ================= 输出 =================
png_path = OUT_DIR / "05_data_lineage_diagram.png"
pdf_path = OUT_DIR / "05_data_lineage_diagram.pdf"
svg_path = OUT_DIR / "05_data_lineage_diagram.svg"
fig.savefig(png_path, dpi=200, bbox_inches="tight", facecolor="white")
fig.savefig(pdf_path, bbox_inches="tight", facecolor="white")
fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
print("wrote:", png_path)
print("wrote:", pdf_path)
print("wrote:", svg_path)
