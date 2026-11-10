# 成员2 清洗与融合质量报告

> 模块：成员2「清洗与融合」。报告日期：2026-10-31。
> 所有数字均来自本模块实际产物的读回核对：Parquet 用 pyarrow/pandas 重读，统计取自各 `*.json`，过程证据取自 `cleaning/logs/`。本报告不做任何新的数据加工；凡未人工逐条核验的项在第 10 节明确列出。
> 口径与例外的来源文档：`data_sources.md`（成员1 采集口径）。

---

## 1. 原始数据只读与产物分层

原始数据全部来自成员1交付的 `data/raw/`（BTS 12 个月度 CSV、NOAA 346 站 CSV、OurAirports 快照、Census 州界 ZIP）。本模块**只读原始文件**，不修改、不覆盖、不删除任何原始件；加工产物按三层落盘：

| 层 | 目录 | 内容 |
|---|---|---|
| 原始层（只读） | `data/raw/` | 成员1 采集的四类原始数据与 manifest |
| 清洗层 | `data/cleaned/` | `bts_flights_2024.parquet`、`noaa_obs_2024.parquet`、`airport_timezones.csv`、`airport_state_check.csv` 及统计 JSON |
| 融合层 | `data/integrated/` | `flights_weather_2024.parquet`（主）、`flights_weather_2024_sample.csv`（前 2 万行查看样本）、`fusion_stats.json` |

可重建脚本（只读复用，本模块未改写）位于 `cleaning/`：`01_clean_bts.py`、`02_clean_noaa.py`、`02_verify_sample.py`、`03_airport_timezones.py`、`03_state_check.py`、`04_fusion_weather.py`。

---

## 2. 先小样本、后全量

每个清洗/融合环节都先在小样本上跑通并人工核对，再跑全量：

| 环节 | 样本证据 | 全量证据 |
|---|---|---|
| BTS 清洗 | `cleaning/logs/bts_sample_check.txt`：3,112 条样本全部保留、flight_id 唯一、arr_del15_mismatch=0 | `cleaning/logs/bts_final_check.txt`：读回全年 parquet，7,079,060 行 × 20 列，核心列非空率如上 |
| NOAA 清洗 | `cleaning/logs/noaa_format_notes.txt`（ATL/WYS/SGU 三站列数与字段解析对照）、`cleaning/logs/noaa_sample_verify.txt`（15 条 METAR 原文交叉核验） | `cleaning/logs/noaa_final_check.txt`、`cleaning/logs/noaa_full_run.log`：346 站合并 3,905,968 行 |
| 时区/州界 | `cleaning/logs/timezone_state_verify.txt`：金标准 5 机场 + point-in-polygon 逐条打印 | 同日志即为全量结果（348 机场） |
| 天气融合 | `cleaning/logs/fusion_check.txt`：时区 4 例、2400 跨日 1 例、天气匹配 3 例、XWA/SGU/WYS 例外各 1 例 | 同日志末尾读回主 parquet：7,079,060 行 × 44 列，flight_id 唯一 |

---

## 3. BTS 清洗质量

读回 `data/cleaned/bts_flights_2024.parquet`：**7,079,060 行 × 20 列**，flight_id 全年唯一（重复 0）。

清洗前后（逐月，来自 `data/cleaned/bts_cleaning_log.csv`，单位：行）：

| 月份 | 原始行数 | 保留行数 | 剔除非2024 | 剔除缺键 | 去重 | 2400航班 | 取消 | 备降 | 到达时间缺失 | ArrDel15不一致 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2024-01 | 547,271 | 547,271 | 0 | 0 | 0 | 0 | 20,389 | 1,512 | 20,633 | 0 |
| 2024-02 | 519,221 | 519,221 | 0 | 0 | 0 | 0 | 3,002 | 950 | 3,133 | 0 |
| 2024-03 | 591,767 | 591,767 | 0 | 0 | 0 | 1 | 5,120 | 1,234 | 5,262 | 0 |
| 2024-04 | 582,185 | 582,185 | 0 | 0 | 0 | 0 | 4,035 | 1,235 | 4,148 | 0 |
| 2024-05 | 609,743 | 609,743 | 0 | 0 | 0 | 0 | 8,244 | 2,273 | 8,340 | 0 |
| 2024-06 | 611,132 | 611,132 | 0 | 0 | 0 | 0 | 7,876 | 1,984 | 7,994 | 0 |
| 2024-07 | 634,613 | 634,613 | 0 | 0 | 0 | 0 | 18,372 | 2,303 | 18,485 | 0 |
| 2024-08 | 619,025 | 619,024 | 0 | 1 | 0 | 0 | 12,714 | 2,008 | 12,870 | 0 |
| 2024-09 | 582,622 | 582,622 | 0 | 0 | 0 | 0 | 3,499 | 861 | 3,543 | 0 |
| 2024-10 | 615,497 | 615,497 | 0 | 0 | 0 | 0 | 6,284 | 699 | 6,332 | 0 |
| 2024-11 | 575,404 | 575,404 | 0 | 0 | 0 | 0 | 2,629 | 842 | 2,713 | 0 |
| 2024-12 | 590,581 | 590,581 | 0 | 0 | 0 | 0 | 4,151 | 1,598 | 4,401 | 0 |
| **合计** | **7,079,061** | **7,079,060** | **0** | **1** | **0** | **1** | **96,315** | **17,499** | **97,854** | **0** |

- 去重：全年重复剔除 0 行；非 2024 记录剔除 0 行。
- 2400 航班：CRSDepTime=2400 原值**全年 1 条**（2024-03-08 HA1004 HNL→LAX，Pacific/Honolulu），已按次日 00:00 处理（sched_dep_local=2024-03-09，dep_utc=2024-03-09 10:00，已匹配天气）；表中 2024-03 的"2400航班=1"即指此条。另有 **12,331 条 `crs_dep_hhmm<100` 的凌晨时刻航班**（如 28=00:28、24=00:24），均按**当日** 00:xx 处理，不是 2400、也不跨日。
- 取消 96,315、备降 17,499、到达时间缺失 97,854（三者有重叠，非互斥）。
- `arr_del15_mismatch` 全年=0：到达延误值与 ArrDel15 标志完全一致。
- 剔除说明：仅 2024-08 有 1 行身份键（航班号等）缺失，按规则剔除并计数；其余全部保留。
- 关键列非空率（读回）：flight_id/flight_date/origin/dest/州/时间 100%；tail_number 99.72%；arr_delay_min 与 arr_del15 98.39%（空值即取消/备降/到达时间缺失航班，属预期）。

---

## 4. NOAA 清洗质量

读回 `data/cleaned/noaa_obs_2024.parquet`：**3,905,968 行 × 19 列**，346 个站，obs_utc 覆盖 2024-01-01 00:00 ~ 2024-12-31 23:59。

- ISD 规则出处：官方 ISD Format Document（`https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf`），字段解析对照见 `cleaning/logs/noaa_format_notes.txt`。
- 报告类型过滤：原始全部报告类型 4,529,560 行 → 仅保留 FM-15（3,204,352）与 FM-16（701,616）共 3,905,968 行；剔除 FM-12（483,321）、SOD（119,322）、FM-13（8,311）、SHEF（6,893）、SOM（3,504）、SY-MT（2,233）、MESOW（8）。
- 各变量缺失率（读回非空率换算）：

| 变量 | 非空率 | 缺失率 |
|---|---:|---:|
| 气温 temp_c | 99.54% | 0.46% |
| 露点 dew_c | 99.29% | 0.71% |
| 海平面气压 slp_hpa | 72.99% | 27.01% |
| 风向 wind_dir_deg | 81.82% | 18.18% |
| 风速 wind_speed_kts | 99.44% | 0.56% |
| 能见度 vis_m | 99.81% | 0.19% |
| 降水 precip_mm | 74.50% | 25.50% |

- 质量码：各要素保留原始 ISD 质量码（如 temp_q/vis_q/wind_speed_q/precip_q）。融合后 matched 子集的质量码分布见 `fusion_stats.json` 的 `quality_code_dist_in_matched`（以 `5`/`1` 通过检查为主，`9` 为缺测）。
- 缺测≠无雨口径：AA1 降水段整段缺失 → `precip_mm=NaN` 且 `precip_reported=0`；AA1 存在（含 depth=0）→ `precip_reported=1`。**`precip_reported=0` 是缺测，不得当作无雨。**
- VIS 单位：官方文档明确 UNITS=Meters 且无倍率，码值直接=米（实证 ATL `016093` 对应 METAR `10SM`=16093m）；早期任务书"VIS×10"的说法与官方文档矛盾，已按文档纠正。
- 样本 METAR 交叉核验：抽 15 条（LAX/ORD/JFK，冬夏各半，含 FM-16），温度/露点/风/能见度/气压全部在容差内一致（15/15），见 `cleaning/logs/noaa_sample_verify.txt`。

---

## 5. 时区转换

- 来源：348 机场坐标全部来自 `metadata/airport_station_mapping_reviewed.csv`（未触发 OurAirports 回退），用 timezonefinder 解析 IANA 时区，**348/348 成功，失败 0**，共 22 个唯一时区（含 AK/HI/PR/VI/GU/AS/MP 等领地）。
- 金标准核验（`cleaning/logs/timezone_state_verify.txt`）：JFK=America/New_York、ORD=America/Chicago、LAX=America/Los_Angeles、DEN=America/Denver、PHX=America/Phoenix，5/5 PASS。
- 夏令时/2400/跨日：`sched_dep_local` 由航班日期+HHMM 拼成本地时刻，经 zoneinfo 转 `dep_utc`。
  - 冬季/夏季抽样（融合日志）：JFK 冬令时 EST、ORD/LAX 夏令时、PHX 无夏令时 MST，UTC 换算 4/4 正确。
  - 2400/跨日样例（真实 CRSDepTime=2400）：`2024-03-08_HA_1004_HNL_LAX_2400`，本地 2024-03-09 00:00 HST → UTC 2024-03-09 10:00。另注：`crs_dep_hhmm=28` 的航班（如 `2024-01-01_AA_154_DEN_MIA_0028`）为**当日** 00:28（DEN→UTC 07:28），不是 2400、不跨日。
  - 夏令时回退夜（11 月第一个周日 1:00–1:59 本地）按标准时间解释。
- 读回断言：融合表 `dep_utc` 为 NaT 的行数 = **0**；`origin_tz_iana` 缺失 = 0。

---

## 6. 天气匹配

- 规则（`cleaning/04_fusion_weather.py`）：按出发地机场对应站，取**计划起飞前最近一条 FM-15/FM-16 观测**，时间差 ≤90 分钟；同时刻重复观测优先 FM-15；60 分钟窗口作为敏感性字段。
- 机场匹配率：7,074,065 / 7,079,060 = **99.929%** 的航班对应正式 346 站清单内的可用站。
- 匹配率（读回 `weather_match_status`）：

| 状态 | 行数 | 占比 | 含义 |
|---|---:|---:|---|
| matched | 7,055,161 | 99.662% | 90 分钟内匹配到观测 |
| no_obs_within_90 | 18,904 | 0.267% | 最近观测 >90 分钟（观测附带但偏陈旧） |
| no_station_usable | 3,023 | 0.043% | SGU 不在正式 346 站清单，无观测 |
| no_station | 1,972 | 0.028% | XWA 无可用站，无观测 |

- 窗口匹配率：90 分钟 99.662%；60 分钟（`weather_match_within_60=True`）**7,047,642 班 = 99.556%**。
- 时间差 gap 分布（matched 子集，分钟）：min 0、P10 5、中位 25、P90 52、max 90；分箱 0–30min 占 57.558%、30–60min 占 42.336%、60–90min 占 0.107%。
- matched 子集天气要素缺失率：气温 0.129%、能见度 0.025%、风速 0.113%、降水 9.025%（降水缺失多为 AA1 缺测，非无雨）。
- 敏感性字段：`weather_match_within_60`（bool）供 60 分钟窗口复算；`weather_gap_minutes` 供自定义阈值。

---

## 7. 融合数据一致性

读回 `data/integrated/flights_weather_2024.parquet`：**7,079,060 行 × 44 列**，与 BTS 清洗行数完全一致（一行一班），flight_id 唯一（重复 0）。

- 行数断言：7,079,060 = BTS 清洗行数；无航班因天气缺失被丢弃。
- 44 列契约：20 列沿用 BTS + `origin_polygon_state`、`origin_tz_iana`、`dep_utc`、`weather_match_status`、`station_id`、`weather_obs_utc`、`weather_gap_minutes`、`weather_match_within_60` + 13 个天气要素列（含各自质量码与降水辅助列）。逐字段见 `docs/field_dictionary.md`。
- 主格式 Parquet；另导出前 20,000 行 `flights_weather_2024_sample.csv` 供快速查看（**非全量，不用于统计**）。
- 观测去重：NOAA 清洗 3,905,968 行 → 融合前按 `(station_id, obs_utc)` 去重（FM-15 优先）→ 3,898,753 行（移除 7,215 条重复时刻）。

---

## 8. 州界关联

- 方法：Census `cb_2024_us_state_500k`（56 个州/州级等同地区多边形，NAD83 十进制度）对机场 WGS84 坐标做 point-in-polygon（pyshp 读 SHP + shapely STRtree 粗筛后 contains/touches）。
- 坐标系说明：州界 NAD83、机场坐标 WGS84，均为十进制度；1:500k 比例尺下偏差远小于制图误差，本次**未做投影/基准转换**，近似按同一经纬度处理。
- 结果（348 机场）：落入多边形内 348；与 BTS 州一致 345；不一致 0；不适用 `na` 3。
- 融合表州界列：`origin_polygon_state` 缺失 0；全表州归属不一致 1,223 行，**全部为 TT 领地机场（GUM/PPG/SPN）的编码差异**（BTS `TT` vs Census `GU/AS/MP`），非位置错误；其余 7,077,837 行一致。

---

## 9. 例外处理（如实保留，不补造）

| 机场/站 | 情况 | 融合处理 | 行数 |
|---|---|---|---:|
| XWA | 当前规则下无可用 NOAA 站（不以旧 ISN 机场顶替） | `weather_match_status=no_station`，天气列全空 | 1,972 |
| SGU / 72475423186 | 位置资料冲突，**不在正式 346 站清单**（试采集文件已跳过） | `no_station_usable`，天气列全空 | 3,023 |
| WYS / 72676494163 | 仅 2024-04-29 ~ 11-06 有观测，覆盖外时段无记录 | 覆盖外自然落入 `no_obs_within_90`，**不补造天气** | 313（matched 307 / no_obs_within_90 6） |

- 任何"无天气记录"一律保留为缺失，不填成晴天、无雨或零风速。

---

## 10. 已核验 与 未核验 清单

### 已通过断言/抽样核验

- BTS：行数 7,079,060、20 列、flight_id 唯一、2400/取消/备降/到达缺失计数、ArrDel15 一致性=0、剔除 1 行缺键。
- NOAA：行数 3,905,968、19 列、346 站、报告类型分布、各变量缺失率、VIS=米口径、15 条 METAR 样本 15/15 一致。
- 时区：348/348 成功、金标准 5/5 PASS、dep_utc NaT=0、冬夏令时与 2400 跨日抽样正确。
- 融合：行数 7,079,060、44 列、flight_id 唯一、weather_match_status 四项计数（读回与 fusion_stats.json 一致）、dep_utc 无 NaT、60 分钟匹配数 7,047,642、gap 分布、观测去重 3,905,968→3,898,753。
- 州界：point-in-polygon 348 落入、345 一致/0 不一致/3 个 TT na、融合表 1,223 行不一致全为 TT 编码差异。
- 例外：XWA/SGU/WYS 三类例外行数与状态分布经读回复核一致。

### 尚未人工逐条核验（如实声明）

- 全量 390 万条观测的质量码**未逐条人工复核**；质量码分布已统计，`A/C/P/U/I/2/6/7` 等非 `5/1/9` 码仅作分布记录，未逐一研判。
- `no_obs_within_90` 行附带的陈旧观测（gap>90 分钟，中位约 194 分钟，最长约 6 天）未做合理性人工抽查。
- 时区回退夜歧义时刻仅按规则解释，未逐行枚举核对；州界 NAD83/WGS84 近似未投影，边界附近机场未做投影后复测。
- **时间差匹配成功 ≠ 天气字段全部可用 ≠ 模型结论**：matched 子集仍有约 0.1%–9% 的单要素缺失（尤其降水），且天气代表的是起飞前最近观测，不等于起飞瞬时天气。后续建模需自行过滤质量码与缺失，并就 60/90 分钟窗口、陈旧观测做敏感性分析。

---

## 11. 统一后续分析数据使用规则（供成员3/4/5）

完整规则见 `README_member2.md` 第八节；此处为验收用简表，数字来自 `cleaning/05_quality_code_usage.py`（基数=matched 7,055,161 行，结果落盘 `data/integrated/quality_code_usage_stats.json`、`cleaning/logs/quality_code_usage.txt`）。

**(1) 天气质量码四类规则**（依据官方 ISD Format Document；不可只凭天气数值非空认定有效）

| 分类 | 码值 | temp | vis | wind_speed | precip |
|---|---|---:|---:|---:|---:|
| 可用 usable | 0/1/4/5/C/A | 99.777% | 99.888% | 99.877% | 90.846% |
| 不确定 uncertain | 2/6/M/I/P/R/U | 0.037% | 0.085% | 0.010% | 0.129% |
| 不可用 erroneous | 3/7 | 0.058% | 0.015% | 0.000%(25行) | 0 |
| 缺测 missing | 9/空 | 0.129% | 0.012% | 0.113% | 9.025% |

**(2) 天气窗口**：仅 `weather_match_status=='matched'`（gap≤90min）为有效天气；`no_obs_within_90`（18,904，gap 中位约 194min）为陈旧观测仅作诊断；航班级统计每航班一行。

**(3) 降水时段**：主分析只用 `precip_period_h==1`（1h 累计，6,406,220 行=90.802%）；3h/6h/24h 累计（合计 12,773 行）不得与 1h 混作同一小时降水量；`precip_reported=0` 是缺测≠无雨。

**(4) 延误口径**：`arr_del15`/`arr_delay_min` 仅用于非取消、非备降、到达时间存在的航班；取消率/备降率用 `cancelled`/`diverted` 单列、分母为全部航班，不并入准点率分母。

---

## 关键文件清单（相对项目根目录）

```
data/cleaned/bts_flights_2024.parquet        # BTS 清洗结果 7,079,060×20
data/cleaned/bts_cleaning_log.csv            # BTS 逐月清洗计数
data/cleaned/bts_clean_stats.json             # BTS 汇总统计
data/cleaned/noaa_obs_2024.parquet           # NOAA 清洗结果 3,905,968×19
data/cleaned/noaa_clean_stats.json            # NOAA 汇总统计
data/cleaned/airport_timezones.csv           # 348 机场 IANA 时区
data/cleaned/airport_state_check.csv          # 348 机场州界 point-in-polygon
data/cleaned/airport_timezone_stats.json     # 时区/州界汇总统计
data/integrated/flights_weather_2024.parquet # 融合主表 7,079,060×44
data/integrated/flights_weather_2024_sample.csv  # 前 2 万行查看样本
data/integrated/fusion_stats.json            # 融合匹配率/gap/质量码分布
data/integrated/quality_code_usage_stats.json  # matched 子集质量码四类归类统计
cleaning/01_clean_bts.py … 05_quality_code_usage.py  # 可重建脚本（05=质量码归类）
cleaning/logs/*.txt / *.log                  # 样本与全量核验日志（含 quality_code_usage.txt）
docs/field_dictionary.md                     # 本模块字段字典
docs/05_data_lineage_diagram.{png,pdf,svg,py}  # 多源数据关联图/血缘图（PNG/PDF 可查看，py/svg 可编辑源）
```
