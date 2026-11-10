# 成员2 清洗与融合模块运行说明

本说明供组长并入全组 README。范围是把成员1交付的原始 BTS 航班与 NOAA 天气清洗为分析用表、完成机场时区/州界处理，并融合为"一行一班"的航班—天气主表。不包含回归、聚类、可视化或最终结论；口径与例外继承自成员1的 `data_sources.md`。

## 一 模块职责与当前状态

本模块只做四件事：

1. 清洗 BTS 全年航班，统一字段、标记取消/备降/到达缺失、校验 ArrDel15 一致性；
2. 清洗 NOAA Global Hourly 2024，仅保留 FM-15/FM-16，按官方 ISD 文档解析温/露/压/风/能见/降水并保留质量码；
3. 为 348 个机场解析 IANA 时区、做 Census 州界 point-in-polygon 核验，并把计划起飞本地时间转 UTC；
4. 按"起飞前最近 90 分钟内同站 FM-15/FM-16"融合天气，产出一行一班主表。

以下数字均为本模块在本机真实运行后读回的结果，不是照抄任务书：BTS 清洗后 7,079,060 行 × 20 列；NOAA 清洗后 3,905,968 行 × 19 列（346 站）；融合主表 7,079,060 行 × 44 列，天气 90 分钟匹配率 99.662%、60 分钟 99.556%。字段逐列含义见 `docs/field_dictionary.md`，质量验收与已核验/未核验清单见 `docs/quality_report.md`。

## 二 环境与依赖

实际运行环境：Windows，Python 3.13.16。与成员1采集脚本（纯标准库）不同，本模块需要数据与地理处理库：

| 依赖 | 用途 | 本机版本 |
|---|---|---|
| pandas | 表格清洗与融合 | 3.1.0 |
| pyarrow | Parquet 读写 | 26.0.0 |
| zoneinfo + tzdata | 本地时间转 UTC、夏令时 | 标准库 + tzdata |
| timezonefinder | 机场经纬度→IANA 时区 | 9.2.0 |
| pyshp（shapefile） | 读 Census SHP | 3.1.6 |
| shapely | point-in-polygon 空间判定 | 2.2.0 |

在项目根目录（含 `data/`、`cleaning/` 的目录）运行命令；不把个人盘符或姓名写死在脚本中。

一次性安装本模块第三方依赖（脚本实际 import 的库；`openpyxl` 本模块未使用，不必安装）：

```bat
pip install pandas pyarrow numpy tzdata timezonefinder pyshp shapely
```

原始数据需由成员1先就位（只读，本模块不下载）：

| 相对路径 | 内容 |
|---|---|
| `data/raw/BTS/BTS_2024_full_year/` | 12 个月度 BTS CSV（脚本按 `On_Time_Reporting_Carrier_On_Time_Performance_(1987_present)_2024_{m}.csv` 逐月读取，m=1..12） |
| `data/raw/NOAA/2024/{station_id}.csv` | 正式 346 站 2024 天气 CSV（另 `isd-history.csv` 为站点目录） |
| `data/raw/OurAirports/airports.csv` | 机场坐标回退源（本次全部命中 mapping_reviewed，未触发回退） |
| `data/raw/Census/cb_2024_us_state_500k.zip` | NAD83 州界 ZIP（含 SHP/SHX/DBF/PRJ） |
| `metadata/bts_airports_2024.csv`、`metadata/airport_station_mapping_reviewed.csv`、`metadata/noaa_full_airports_2024.csv`、`metadata/census_states_2024.csv` | 348 机场权威清单、机场—站点修订映射、正式 346 站清单、州代码参考 |

## 三 交付物清单

| 相对路径 | 内容 | 关键统计 |
|---|---|---|
| `data/cleaned/bts_flights_2024.parquet` | BTS 清洗航班表 | 7,079,060 行 × 20 列；取消 96,315、备降 17,499、到达缺失 97,854；ArrDel15 不一致 0 |
| `data/cleaned/bts_cleaning_log.csv` | BTS 逐月清洗计数 | 12 个月；仅 2024-08 剔除 1 行缺键 |
| `data/cleaned/bts_clean_stats.json` | BTS 汇总统计 | 原始 7,079,061→保留 7,079,060 |
| `data/cleaned/noaa_obs_2024.parquet` | NOAA 清洗观测表 | 3,905,968 行 × 19 列；FM-15 3,204,352、FM-16 701,616；346 站 |
| `data/cleaned/noaa_clean_stats.json` | NOAA 汇总统计 | 原始 4,529,560→保留 3,905,968 |
| `data/cleaned/airport_timezones.csv` | 348 机场时区表 | 348/348 解析成功，22 个唯一时区 |
| `data/cleaned/airport_state_check.csv` | 348 机场州界核验 | 345 一致 / 0 不一致 / 3 个 TT 领地 na |
| `data/cleaned/airport_timezone_stats.json` | 时区/州界汇总 | 金标准 5 机场全 PASS |
| `data/integrated/flights_weather_2024.parquet` | 融合主表（一行一班） | 7,079,060 行 × 44 列；matched 99.662% |
| `data/integrated/flights_weather_2024_sample.csv` | 前 2 万行查看样本 | 仅查看，不用于统计 |
| `data/integrated/fusion_stats.json` | 融合匹配率/gap/质量码分布 | 90min 99.662%、60min 99.556% |
| `data/integrated/quality_code_usage_stats.json` | matched 子集四要素质量码归类统计 | 见 `cleaning/05_quality_code_usage.py` 输出 |
| `cleaning/05_quality_code_usage.py` | 质量码四类归类可重建脚本 | 输出上方 JSON 与日志 |
| `docs/05_data_lineage_diagram.{png,pdf,svg,py}` | 多源数据关联图/血缘图 | PNG/PDF 可直接查看；py/svg 为可编辑源；OurAirports 为未触发的回退路径 |
| `cleaning/logs/` | 样本与全量核验日志（含 `quality_code_usage.txt`） | BTS/NOAA/时区州界/融合/质量码各自自检 |
| `docs/field_dictionary.md` | 本模块全部字段字典 | 覆盖 5 张表 |
| `docs/quality_report.md` | 质量报告（10 项口径） | 含已核验/未核验清单 |
| `metadata/member2_deliverable_checksums.sha256` | 本模块交付文件 SHA-256 清单 | 见文件内条数 |

## 四 复现步骤

按顺序在项目根目录运行（先小样本核验，后全量；命令已与脚本实际参数逐一核对）：

```bat
:: 1) BTS 清洗：--mode 为必填参数（argparse required=True），先样本后全量
python cleaning\01_clean_bts.py --mode sample
python cleaning\01_clean_bts.py --mode full

:: 2) NOAA：先做 METAR 原文交叉核验，再跑全量（02_clean_noaa.py 不传参默认 samples，全量须显式 full）
python cleaning\02_verify_sample.py
python cleaning\02_clean_noaa.py full

:: 3) 机场时区表 → Census 州界核验 → 汇总写日志/统计（均无命令行参数；
::    注意 03_finalize.py 依赖前两步生成的 cleaning/_tz_summary.json 与 _state_summary.json，必须在其后运行）
python cleaning\03_airport_timezones.py
python cleaning\03_state_check.py
python cleaning\03_finalize.py

:: 4) 融合航班—天气（一行一班，无命令行参数）
python cleaning\04_fusion_weather.py

:: 5)（可选/交付）matched 子集质量码四类归类与降水时段统计
python cleaning\05_quality_code_usage.py
```

各步输入、产物与成功判定（判定 = 输出文件存在且自检日志数值符合预期）：

| 步骤 | 输入 | 产物 | 成功判定 |
|---|---|---|---|
| `01_clean_bts.py --mode sample` | `data/samples/raw/member1/BTS/bts_flights_sample.csv` | `cleaning/logs/bts_sample_check.txt` | 日志显示 3,112 行全保留、flight_id unique=True、mismatch=0 |
| `01_clean_bts.py --mode full` | `data/raw/BTS/BTS_2024_full_year/` 12 个 CSV | `data/cleaned/bts_flights_2024.parquet`、`bts_cleaning_log.csv`、`bts_clean_stats.json`、`cleaning/logs/bts_final_check.txt` | 日志行数 7,079,060、20 列、flight_id 唯一、月度和=合并行数、缺键剔除=1 |
| `02_verify_sample.py` | 样本站原始 CSV（LAX/ORD/JFK 三站） | `cleaning/logs/noaa_sample_verify.txt` | 15 条抽样温度/露点/风/能见/气压与 METAR 原文全部一致 |
| `02_clean_noaa.py full` | `metadata/noaa_full_airports_2024.csv` + `data/raw/NOAA/2024/*.csv` | `data/cleaned/noaa_obs_2024.parquet`、`noaa_clean_stats.json`、`cleaning/logs/noaa_final_check.txt`、`noaa_full_run.log` | 行数 3,905,968、19 列、346 站、报告类型仅 FM-15/FM-16、SGU 自动跳过 |
| `03_airport_timezones.py` | `metadata/bts_airports_2024.csv`、`airport_station_mapping_reviewed.csv`、`data/raw/OurAirports/airports.csv` | `data/cleaned/airport_timezones.csv`、`cleaning/_tz_summary.json` | 348 行、时区成功 348/失败 0、金标准 JFK/ORD/LAX/DEN/PHX 全 PASS |
| `03_state_check.py` | `airport_timezones.csv`、`data/raw/Census/cb_2024_us_state_500k.zip`、`metadata/census_states_2024.csv` | `data/cleaned/airport_state_check.csv`、`cleaning/_state_summary.json` | 348 行、inside=348、一致 345/不一致 0/TT 领地 na=3；临时目录自动清理 |
| `03_finalize.py` | 上两步两个 CSV + 两个 `_*_summary.json` | `cleaning/logs/timezone_state_verify.txt`、`data/cleaned/airport_timezone_stats.json` | 日志含金标准 5/5 PASS、TT 三机场编码差异说明；stats JSON 可读 |
| `04_fusion_weather.py` | 全部清洗表 + 机场—站点映射 + 346 站清单 | `data/integrated/flights_weather_2024.parquet`、`flights_weather_2024_sample.csv`、`fusion_stats.json`、`cleaning/logs/fusion_check.txt` | 主表 7,079,060×44、flight_id 唯一、`dep_utc` 无 NaT、matched=7,055,161 |
| `05_quality_code_usage.py` | 融合主表（仅 matched 子集） | `data/integrated/quality_code_usage_stats.json`、`cleaning/logs/quality_code_usage.txt` | 四要素可用占比、不可用/不确定占比、降水 period 分布落盘 |

脚本默认读既有产物路径；重复运行会覆盖本模块自己的产出，但不触碰 `data/raw/`。如需重跑，确认 `data/raw/` 与上述 `metadata/` 文件完整即可。

## 五 口径与例外（继承成员1）

- **天气匹配**：取计划起飞前最近一条同站 FM-15/FM-16，时间差 ≤90 分钟；同时刻重复 FM-15 优先；60 分钟窗口由 `weather_match_within_60` 字段提供。
- **时间口径**：`sched_dep_local` 为机场本地计划时刻，`dep_utc` 为其 UTC；夏令时/24:00 跨日由 zoneinfo 处理；夏令时回退夜按标准时间解释。CRSDepTime=2400 原值全年 1 条（2024-03-08 HA1004 HNL→LAX）已按次日 00:00 处理；`crs_dep_hhmm<100` 的凌晨航班（12,331 条，如 28=00:28）按当日 00:xx 处理，非 2400。
- **降水缺测≠无雨**：`precip_reported=0` 表示 AA1 降水段缺测（`precip_mm` 为空），不得当作无雨；`precip_reported=1` 且 `precip_mm=0` 才是实测无降水。
- **VIS 单位**：按官方 ISD 文档，能见度码值直接=米，不做 ×10。
- **州界坐标系**：Census 州界 NAD83、机场坐标 WGS84，均为十进制度，500k 比例尺下近似按同一经纬度处理，未做投影转换。
- **三类例外如实保留**：XWA 无可用站（1,972 班，保留航班不顶替旧站）；SGU 不在正式 346 站清单（3,023 班，无观测）；WYS 仅 2024-04-29~11-06 有观测（覆盖外自然落入未匹配，不补造天气）。无天气记录一律留空，不填晴天/无雨/零风。
- **TT 领地**：GUM/PPG/SPN 的 BTS 州码为聚合 `TT`，Census 多边形分别为 GU/AS/MP，属编码体系差异，非位置错误。

## 六 已知限制

- 全量约 390 万条观测的质量码**未逐条人工复核**；分布已统计，`A/C/P/U/I` 等非通过码仅作分布记录。
- `weather_match_status=no_obs_within_90` 的行（18,904）虽附带最近观测，但时间差 >90 分钟（中位约 194 分钟），属陈旧观测；建模前应按 `weather_match_status=='matched'` 或 `weather_match_within_60` 过滤。
- 时区回退夜歧义时刻、州界边界附近机场未做投影后复测；WYS 覆盖不足已披露，未断定其季节停运原因。
- 匹配成功 ≠ 天气字段全部可用 ≠ 模型结论：matched 子集仍有 0.1%–9% 的单要素缺失（尤其降水），天气代表起飞前最近观测而非起飞瞬时。
- 主表 Parquet 为完整结果；`flights_weather_2024_sample.csv` 仅前 2 万行，不能用于任何统计结论。

## 七 自检摘要

四份交付物写完后已读回校验（2026-10-31）：

- 文件存在性：`README_member2.md`、`docs/field_dictionary.md`、`docs/quality_report.md`、`metadata/member2_deliverable_checksums.sha256` 均存在且非空（清单为纯 ASCII、LF 行尾、无 CR）。
- 数字一致性（Parquet 重读 vs 统计 JSON）：BTS 7,079,060×20、NOAA 3,905,968×19、融合 7,079,060×44，flight_id 唯一、dep_utc NaT=0；weather_match_status 四项计数与 `fusion_stats.json` 完全一致（matched 7,055,161 / no_obs_within_90 18,904 / no_station_usable 3,023 / no_station 1,972）；60 分钟匹配 7,047,642；matched 子集缺失率 temp 0.129% / vis 0.025% / wind 0.113% / precip 9.025%，均与 JSON 一致。
- SHA-256 清单：条数与覆盖文件**以 `metadata/member2_deliverable_checksums.sha256` 实际内容为准**（后续若纳入 logs、关联图等新文件会变化，不在此处写死数字）；清单自身不在清单内。
- 未做：全量质量码逐条人工复核、`no_obs_within_90` 陈旧观测合理性抽查、州界投影后复测（见质量报告第 10 节）。

## 八 统一后续分析数据使用规则（供成员3/4/5）

主表 `data/integrated/flights_weather_2024.parquet` 一行一班。后续分析统一遵守以下口径，避免各成员各自解释：

### 8.1 天气质量码规则（不可只凭天气数值非空认定有效）

依据官方 ISD Format Document，把 `temp_q/vis_q/wind_speed_q/precip_q` 单字符质量码分四类（统计脚本 `cleaning/05_quality_code_usage.py`，结果见 `data/integrated/quality_code_usage_stats.json` 与 `cleaning/logs/quality_code_usage.txt`，基数=matched 7,055,161 行）：

| 分类 | 包含码值（官方含义） | 处理建议 |
|---|---|---|
| 可用 usable | `0`通过粗范围、`1`通过全部质控、`4`粗范围(NCEI源)、`5`全部质控(NCEI源)、`C`人工核查、`A`标可疑但接受为可用 | 可直接用于分析 |
| 不确定 uncertain | `2`可疑、`6`可疑(NCEI源)、`M`NWS/FAA人工改值、`I`验证器补插、`P`验证器替换、`R`NCEI软件算得替换、`U`编辑后替换 | 保留但做敏感性分析/标注，不要静默丢弃 |
| 不可用 erroneous | `3`错误、`7`错误(NCEI源) | 按缺失处理，不进入均值/回归 |
| 缺测 missing | `9`缺测，以及 q 为空/NaN | 按缺失处理 |

matched 子集各类占比（实测）：

| 要素 | 可用 | 不确定 | 不可用 | 缺测 |
|---|---:|---:|---:|---:|
| 气温 temp | 99.777% | 0.037% | 0.058% | 0.129% |
| 能见度 vis | 99.888% | 0.085% | 0.015% | 0.012% |
| 风速 wind_speed | 99.877% | 0.010% | 0.000%(25行) | 0.113% |
| 降水 precip | 90.846% | 0.129% | 0 | 9.025% |

> 说明：不可用码占比极低（气温 0.058%、能见度 0.015%、风速 25 行、降水 0），但**不能因为占比小就忽略**；凡做回归/均值，建议至少把 erroneous 当缺失。

### 8.2 天气窗口规则

- 只有 `weather_match_status=='matched'`（gap 0–90 分钟）才算有效天气关联；需要更严窗口用 `weather_match_within_60==True`（99.556%）。
- `no_obs_within_90`（18,904 行）虽附带最近观测，但 gap>90 分钟（中位约 194 分钟，最长约 6 天），属陈旧观测，**不得当有效天气**，仅可用于诊断覆盖率。
- `no_station`(XWA)/`no_station_usable`(SGU) 行天气列全空，按缺失。
- 航班级统计一律按航班口径：主表每航班一行，不要把一条观测重复关联给多个航班。

### 8.3 降水时段规则

- `precip_mm` 可能是 1/3/6/24 小时累计量，由 `precip_period_h` 区分。matched 子集实测分布：1h=90.802%、6h=0.108%、24h=0.038%、3h=0.036%、缺测 9.017%。
- **主分析只用 `precip_period_h==1` 的记录**（6,406,220 行，占 matched 90.802%）；不得把 3/6/24 小时累计量与 1 小时量混作同一小时降水量。
- 缺测继续保留缺失：`precip_reported=0` 是缺测（`precip_mm` 为空），≠ 无雨；只有 `precip_reported==1` 且 `precip_mm==0` 才是实测无降水。

### 8.4 延误分析口径

- `arr_del15` / `arr_delay_min` 仅适用于**非取消、非备降、到达时间存在**的航班（`cancelled==0 & diverted==0 & arrival_time_missing==0`）；这些字段在取消/备降/到达缺失行本就为 NaN。
- 取消率、备降率用 `cancelled`、`diverted` 列**另行统计**，分母是全部航班；准点/延误率分母只取可计算航班，二者不得混用，避免口径混淆。
- `arr_del15_mismatch` 全年为 0（延误值与 ArrDel15 标签一致），可作为数据质量背书，但不影响上述分母规则。
