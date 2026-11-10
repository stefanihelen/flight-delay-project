# 成员2 字段字典（清洗与融合交付表）

> 适用范围：成员2「清洗与融合」模块全部交付表。
> 本字典的列名、类型、行数与缺失率均为 2026-10-31 从实际产物读回核对的结果（Parquet 用 pyarrow 读 schema，CSV 用 pandas 读列）。
> 类型标注说明：Parquet 中的 `dictionary<…>` 列在 pandas 读入后表现为普通字符串/类别值，本字典按"业务取值"描述，不强制读者按编码存储理解。
> 通用缺失口径：Parquet 中数值/时间的缺失为 `NaN`/`NaT`；字符串缺失为空串或 `None`。质量码列保留原始 ISD 码值字符，缺测时也可能保留 `"9"` 等码，需配合数值列是否为 `NaN` 判断，不能只看码。

---

## 1. BTS 清洗表 `data/cleaned/bts_flights_2024.parquet`

规模：7,079,060 行 × 20 列。来源：BTS 官方月度 CSV（Reporting Carrier On-Time Performance 2024），逐月清洗合并。

| # | 字段名 | 中文说明 | 类型/精度 | 单位 | 来源 / 加工规则 | 缺失口径 | 示例 / 备注 |
|---|---|---|---|---|---|---|---|
| 1 | flight_id | 航班唯一主键 | large_string | — | 加工生成：`{FlightDate}_{Reporting_Airline}_{Flight_Number}_{Origin}_{Dest}_{CRSDepTime}` | 100% 非空；全年唯一（重复数=0） | `2024-01-08_9E_4801_LGA_OMA_0856` |
| 2 | flight_date | 航班日期 | date32[day] | 日期 | 原始 `FlightDate` | 100% 非空 | `2024-01-08` |
| 3 | reporting_airline | 承运航司代码 | large_string | — | 原始 `Reporting_Airline`（如 9E、AA、DL） | 100% 非空 | `9E` |
| 4 | flight_number | 航班号 | int64 | 班 | 原始 `Flight_Number_Reporting_Airline` | 100% 非空 | `4801` |
| 5 | tail_number | 注册号（机尾号） | large_string | — | 原始 `Tail_Number` | 非空率 99.72%（少数航班缺注册号，保留为空不删除） | `N485PX` |
| 6 | origin | 出发机场 IATA | large_string | — | 原始 `Origin` | 100% 非空 | `LGA` |
| 7 | dest | 到达机场 IATA | large_string | — | 原始 `Dest` | 100% 非空 | `OMA` |
| 8 | origin_airport_id | 出发机场 ID（BTS 内部编码） | int64 | — | 原始 `OriginAirportID`（与 OurAirports 的 id 不是同一编号体系） | 100% 非空 | `12953` |
| 9 | dest_airport_id | 到达机场 ID | int64 | — | 原始 `DestAirportID` | 100% 非空 | `13871` |
| 10 | origin_state | 出发州/领地代码 | large_string | — | 原始 `OriginState`；海外领地聚合为 `TT` | 100% 非空 | `NY`；GUM/PPG/SPN 为 `TT` |
| 11 | dest_state | 到达州/领地代码 | large_string | — | 原始 `DestState` | 100% 非空 | `NE` |
| 12 | crs_dep_hhmm | 计划起飞时间 HHMM | int64 | HHMM | 原始 `CRSDepTime` 转整数；`2400` 表示午夜 | 100% 非空；全年 `2400` 原值 1 条（2024-03-08 HA1004 HNL→LAX，按次日 00:00）；另有 12,331 条 `<100` 的凌晨时刻（如 28=00:28）按当日 00:xx 处理 | `856` = 08:56 |
| 13 | sched_dep_local | 计划起飞本地时间 | timestamp[us] | 本地时刻 | 加工：`flight_date` + `crs_dep_hhmm` 拼成本地时刻；24:00/跨日按次日 00:xx 处理 | 100% 非空 | `2024-01-08 08:56:00` |
| 14 | distance_miles | 航段距离 | double | 英里 | 原始 `Distance` | 100% 非空 | `1148.0` |
| 15 | arr_delay_min | 到达延误 | double | 分钟 | 原始 `ArrDelay`（到达时刻−计划到达，负值=提前） | 非空率 98.39%；取消/备降/到达时间缺失航班为空 | `-11.0` |
| 16 | arr_del15 | 到达延误≥15 分钟标志 | double(0/1) | — | 原始 `ArrDel15` | 与 `arr_delay_min` 同步缺失（98.39%） | `0.0` |
| 17 | cancelled | 取消标志 | int8(0/1) | — | 原始 `Cancelled` | 100% 非空；全年 96,315 班取消 | `0` |
| 18 | diverted | 备降标志 | int8(0/1) | — | 原始 `Diverted` | 100% 非空；全年 17,499 班备降 | `0` |
| 19 | arrival_time_missing | 到达时间缺失标志 | int8(0/1) | — | 加工：到达时刻/到达延误缺失则置 1 | 100% 非空；全年 97,854 班 | 取消/备降航班多为 1 |
| 20 | arr_del15_mismatch | ArrDel15 与延误值一致性自检标志 | int8(0/1) | — | 加工：`arr_delay_min≥15` 与 `arr_del15` 是否一致，不一致置 1 | 100% 非空；全年不一致=0 | 全表 `0` |

> BTS 清洗口径：原始 7,079,061 行 → 保留 7,079,060 行；剔除非 2024 年 0 行、去重 0 行；仅剔除 1 行身份键（航班号）缺失（2024-08）。逐月行数见 `data/cleaned/bts_cleaning_log.csv`。

---

## 2. NOAA 清洗表 `data/cleaned/noaa_obs_2024.parquet`

规模：3,905,968 行 × 19 列。来源：NOAA/NCEI Global Hourly（ISD）2024，正式 346 站；仅保留 `FM-15`（METAR 例行报）与 `FM-16`（SPECI 特报），剔除 FM-12/SOD/FM-13/SHEF/SOM/SY-MT/MESOW 等非逐次机场报。

| # | 字段名 | 中文说明 | 类型/精度 | 单位 | 来源 / 加工规则 | 缺失口径 | 示例 / 备注 |
|---|---|---|---|---|---|---|---|
| 1 | station_id | 气象站编号 | large_string | — | 原始 `STATION`（USAF+WBAN，保留前导零） | 100% 非空；唯一站 346 个 | `72503014732`（LGA 对应站） |
| 2 | obs_utc | 观测时刻（UTC） | timestamp[us] | UTC | 原始 `DATE` 按 UTC 解析（实证均为完整时间戳，无需从 METAR 补造） | 100% 非空；范围 2024-01-01 00:00 ~ 2024-12-31 23:59 | `2024-01-08 13:51:00` |
| 3 | report_type | 报告类型 | large_string | — | 原始 `REPORT_TYPE` | 100% 为 `FM-15`/`FM-16` | `FM-15` 3,204,352 行；`FM-16` 701,616 行 |
| 4 | temp_c | 气温 | double | 摄氏度 ℃ | 解析 `TMP`（如 `+0089,5`→8.9）；缺失码 +9999→NaN | 非空 99.54%（缺失 0.46%） | `3.3` |
| 5 | temp_q | 气温质量码 | large_string | — | `TMP` 第 2 段质量码 | 保留码值；`5`/`1`=通过检查，`9`=缺测 | `5` |
| 6 | dew_c | 露点温度 | double | ℃ | 解析 `DEW`；+9999→NaN | 非空 99.29%（缺失 0.71%） | `1.0` |
| 7 | dew_q | 露点质量码 | large_string | — | `DEW` 质量码 | 同 temp_q | `5` |
| 8 | slp_hpa | 海平面气压 | double | 百帕 hPa | 解析 `SLP`（如 10203→1020.3）；99999→NaN | 非空 72.99%（缺失 27.01%，本站缺报较多） | `1013.2` |
| 9 | slp_q | 气压质量码 | large_string | — | `SLP` 质量码 | 同 temp_q | `5` |
| 10 | wind_dir_deg | 风向 | double | 度（0–360） | 解析 `WND` 第 1 段；999→NaN（含 VRB 风） | 非空 81.82%（缺失 18.18%） | `350.0`；VRB 为 NaN |
| 11 | wind_dir_q | 风向质量码 | large_string | — | `WND` 第 2 段 | 同 temp_q | `5` |
| 12 | wind_speed_kts | 风速 | double | 节 knots | 解析 `WND` 第 4 段（原始 m/s），换算 ×1.94384 为节；9999→NaN | 非空 99.44%（缺失 0.56%） | `9.9` |
| 13 | wind_speed_q | 风速质量码 | large_string | — | `WND` 第 5 段 | 同 temp_q | `5` |
| 14 | vis_m | 能见度 | double | 米 | 解析 `VIS`；**码值直接=米（官方 UNITS=Meters，无倍率）**，>160000 封顶 160000；999999→NaN | 非空 99.81%（缺失 0.19%） | `16093.0`（=10SM） |
| 15 | vis_q | 能见度质量码 | large_string | — | `VIS` 质量码 | 同 temp_q | `5` |
| 16 | precip_mm | 降水量 | double | 毫米 mm | 解析 `AA1` 第 2 段（原始毫米×10）；9999→NaN | 非空 74.50%（缺失 25.50%） | `0.0`（AA1 存在但无降水） |
| 17 | precip_q | 降水质量码 | string | — | `AA1` 第 4 段质量码 | AA1 整段缺失时该列为空 | `5` |
| 18 | precip_period_h | 降水累计时段 | double | 小时 | 解析 `AA1` 第 1 段；99→NaN | 随 AA1 缺失 | `1.0` |
| 19 | precip_reported | 降水是否有报告标志 | int64(0/1) | — | 加工：AA1 整段存在（含 depth=0）置 1；AA1 整段缺失置 0 | 100% 非空 | **0=缺测，不代表无雨** |

> 关键口径：`precip_reported=0` 表示该时次**没有 AA1 降水段（缺测）**，`precip_mm` 必为 NaN；不能把 0 当作"无雨"。`precip_reported=1` 但 `precip_mm=0` 才是"有报告且实测无降水"。另有少量行 AA1 存在但 depth 缺测（质量码 9），此时 `precip_reported=1` 而 `precip_mm` 仍为 NaN。
> 规则出处：NOAA ISD Format Document（`https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf`），解析对照见 `cleaning/logs/noaa_format_notes.txt`；15 条样本 METAR 原文交叉核验全部一致，见 `cleaning/logs/noaa_sample_verify.txt`。

---

## 3. 机场时区表 `data/cleaned/airport_timezones.csv`

规模：348 行 × 8 列。348 个 BTS 机场，时区 100% 由 timezonefinder 解析成功。

| # | 字段名 | 中文说明 | 类型 | 单位 | 来源 / 加工规则 | 缺失口径 | 示例 / 备注 |
|---|---|---|---|---|---|---|---|
| 1 | airport_code | 机场 IATA 代码 | str | — | BTS 全年提取 | 100% | `ABE` |
| 2 | bts_airport_id | BTS 机场 ID | int64 | — | BTS 原始 AirportID | 100% | `10135` |
| 3 | lat | 机场纬度 | float64 | 十进制度 | `metadata/airport_station_mapping_reviewed.csv` 复核坐标（未触发 OurAirports 回退） | 100% | `40.651773` |
| 4 | lon | 机场经度 | float64 | 十进制度 | 同上 | 100% | `-75.442797` |
| 5 | coord_source | 坐标来源 | str | — | 固定 `mapping_reviewed` | 100% | `mapping_reviewed` |
| 6 | tz_iana | IANA 时区名 | str | — | timezonefinder 按经纬度解析 | 100% 成功（失败 0）；共 22 个唯一时区 | `America/New_York` |
| 7 | tz_method | 时区获取方法 | str | — | 固定 `timezonefinder` | 100% | `timezonefinder` |
| 8 | tz_note | 备注 | float64/空 | — | 无特殊备注时为空 | 空为主 | — |

> 金标准核验：JFK=America/New_York、ORD=America/Chicago、LAX=America/Los_Angeles、DEN=America/Denver、PHX=America/Phoenix，5/5 PASS。

---

## 4. 机场州界核验表 `data/cleaned/airport_state_check.csv`

规模：348 行 × 9 列。方法：Census `cb_2024_us_state_500k` 州界多边形（NAD83 十进制度）对机场 WGS84 坐标做 point-in-polygon（pyshp + shapely）。

| # | 字段名 | 中文说明 | 类型 | 单位 | 来源 / 加工规则 | 缺失口径 | 示例 / 备注 |
|---|---|---|---|---|---|---|---|
| 1 | airport_code | 机场 IATA 代码 | str | — | BTS 全年提取 | 100% | `ABE` |
| 2 | bts_airport_id | BTS 机场 ID | int64 | — | BTS 原始 | 100% | `10135` |
| 3 | lat | 机场纬度 | float64 | 十进制度 | 复核坐标（WGS84） | 100% | `40.651773` |
| 4 | lon | 机场经度 | float64 | 十进制度 | 复核坐标（WGS84） | 100% | `-75.442797` |
| 5 | polygon_state | 多边形归属州/领地代码 | str | — | point-in-polygon 命中的 Census STUSPS | 100% | `PA` |
| 6 | polygon_state_name | 州/领地全称 | str | — | Census NAME | 100% | `Pennsylvania` |
| 7 | bts_state | BTS 报送州代码 | str | — | BTS 原始 OriginState（领地聚合 `TT`） | 100% | `PA` |
| 8 | state_consistent | 州归属是否一致 | str(`1`/`0`/`na`) | — | 加工：polygon_state 与 bts_state 比对；`TT` 领地记 `na` | `1`=345，`0`=0，`na`=3（GUM/PPG/SPN） | `1` |
| 9 | note | 判定备注 | str | — | how/crs/编码差异说明 | 100% | `how=inside;crs=NAD83/WGS84近似未投影` |

> 坐标系说明：州界为 NAD83、机场坐标为 WGS84，两者均为十进制度，在 1:500k 比例尺下偏差远小于制图误差，本次**未做投影/基准转换**，近似按同一经纬度处理。
> TT 编码差异：BTS 用 `TT` 聚合海外领地，Census 为三个独立多边形（GUM→GU、PPG→AS、SPN→MP），属编码体系差异而非位置错误。

---

## 5. 融合主表 `data/integrated/flights_weather_2024.parquet`

规模：7,079,060 行 × 44 列，**一行一班**。= BTS 清洗表（20 列）+ 出发地时区/州界（2 列）+ 本地转 UTC（1 列）+ 天气匹配结果与观测（21 列）。另有查看用样本 `data/integrated/flights_weather_2024_sample.csv`（仅前 20,000 行，非全量）。

### 5.1 航班基础列（沿用 BTS 清洗口径，列序 0–22 中除新增外）

| 列 | 字段名 | 中文说明 | 类型 | 备注 |
|---|---|---|---|---|
| 0 | flight_id | 航班主键 | large_string | 同 BTS；全年唯一 |
| 1 | flight_date | 航班日期 | date32[day] | 同 BTS |
| 2 | reporting_airline | 航司 | dictionary(str) | 同 BTS |
| 3 | flight_number | 航班号 | int64 | 同 BTS |
| 4 | tail_number | 注册号 | large_string | 同 BTS |
| 5 | origin | 出发机场 | dictionary(str) | 同 BTS |
| 6 | dest | 到达机场 | dictionary(str) | 同 BTS |
| 7 | origin_airport_id | 出发机场 ID | int64 | 同 BTS |
| 8 | dest_airport_id | 到达机场 ID | int64 | 同 BTS |
| 9 | origin_state | 出发州代码（BTS） | dictionary(str) | 含 `TT` |
| 10 | dest_state | 到达州代码（BTS） | dictionary(str) | 同 BTS |
| 13 | crs_dep_hhmm | 计划起飞 HHMM | int64 | 同 BTS |
| 14 | sched_dep_local | 计划起飞本地时间 | timestamp[us] | 同 BTS；含 24:00/跨日处理 |
| 16 | distance_miles | 距离 | double | 英里 |
| 17 | arr_delay_min | 到达延误 | double | 分钟 |
| 18 | arr_del15 | 延误≥15 标志 | double | 0/1 |
| 19 | cancelled | 取消标志 | int8 | 0/1 |
| 20 | diverted | 备降标志 | int8 | 0/1 |
| 21 | arrival_time_missing | 到达时间缺失标志 | int8 | 0/1 |
| 22 | arr_del15_mismatch | 一致性自检标志 | int8 | 全年=0 |

### 5.2 新增：时区、州界与 UTC 转换列

| 列 | 字段名 | 中文说明 | 类型 | 单位 | 加工规则 / 口径 | 缺失口径 | 示例 |
|---|---|---|---|---|---|---|---|
| 11 | origin_polygon_state | 出发地多边形归属州 | dictionary(str) | — | 来自 `airport_state_check.csv` 的 `polygon_state` | 100% 非空 | `NY`；TT 三机场记 `GU/AS/MP` |
| 12 | origin_tz_iana | 出发地 IANA 时区 | dictionary(str) | — | 来自 `airport_timezones.csv` 的 `tz_iana` | 100% 非空 | `America/New_York` |
| 15 | dep_utc | 计划起飞 UTC 时刻 | timestamp[us] | UTC | 加工：`sched_dep_local` 按 `origin_tz_iana` 转 UTC；夏令时/24:00 跨日由 zoneinfo 正确处理；夏令时回退夜（11 月第一个周日 1:00–1:59 本地）按标准时间解释 | **NaT=0**（无缺失） | `2024-01-08 13:56:00` |

> `flight_id` 构成：`{flight_date}_{reporting_airline}_{flight_number}_{origin}_{dest}_{crs_dep_hhmm}`。
> `sched_dep_local` 为机场本地计划时刻；`dep_utc` 为其 UTC 换算结果。真实 2400 跨日样例：`2024-03-08_HA_1004_HNL_LAX_2400`，HNL `crs_dep_hhmm=2400`→本地 `2024-03-09 00:00`→UTC `2024-03-09 10:00`。另：`crs_dep_hhmm=28`（如 `2024-01-01_AA_154_DEN_MIA_0028`）是**当日** 00:28（DEN→UTC 07:28），不是 2400。

### 5.3 新增：天气匹配结果列

| 列 | 字段名 | 中文说明 | 类型 | 单位 | 加工规则 / 口径 | 取值 / 缺失 |
|---|---|---|---|---|---|---|
| 23 | weather_match_status | 天气匹配状态 | dictionary(str) | — | 起飞前最近一条同站 FM-15/FM-16 观测；同时间 FM-15 优先；窗口上限 90 分钟 | `matched`=7,055,161（99.662%）；`no_obs_within_90`=18,904（0.267%，最近观测 >90 分钟，观测仍附带但偏陈旧）；`no_station_usable`=3,023（SGU 不在正式 346 站清单，无观测）；`no_station`=1,972（XWA 无可用站，无观测） |
| 24 | station_id | 匹配到的气象站 | dictionary(str) | — | 来自机场—站点映射；XWA 无站为空 | XWA 1,972 行为空；其余非空 |
| 25 | weather_obs_utc | 匹配观测时刻 UTC | timestamp[ns] | UTC | merge_asof 选中的观测时刻 | `no_station`/`no_station_usable` 行空；`no_obs_within_90` 行一般有值（但偏陈旧，3 行无观测为空） |
| 26 | weather_gap_minutes | 起飞与观测的时间差 | float | 分钟 | `dep_utc − weather_obs_utc`（观测早于起飞） | matched 行 0–90；no_obs_within_90 行 >90（中位 194，最大 8,633）；无站行为空 |
| 27 | weather_match_within_60 | 是否 60 分钟内匹配 | bool | — | 加工：matched 且 gap≤60 为 True | True=7,047,642（99.556%），False=31,418（敏感性分析用 60 分钟窗口） |

> 使用天气前的过滤建议：仅用 `weather_match_status=='matched'`（gap 0–90）做关联；若用 60 分钟窗口则用 `weather_match_within_60==True`。`no_obs_within_90` 行虽带观测，但 gap>90 分钟（中位约 3.2 小时），属陈旧观测，不应直接当作当次起飞天气。

### 5.4 新增：匹配观测的天气要素列（单位与 NOAA 清洗表一致）

| 列 | 字段名 | 中文说明 | 类型 | 单位 | 缺失口径（matched 子集） | 备注 |
|---|---|---|---|---|---|---|
| 28 | temp_c | 气温 | float | ℃ | 缺失 0.129%（9,072/7,055,161） | |
| 29 | temp_q | 气温质量码 | dictionary(str) | — | `5`/`1` 为主（通过检查），`9`=缺测 | |
| 30 | dew_c | 露点 | float | ℃ | 随原始缺测 | |
| 31 | dew_q | 露点质量码 | dictionary(str) | — | | |
| 32 | slp_hpa | 海平面气压 | float | hPa | 原始缺测较多 | |
| 33 | slp_q | 气压质量码 | dictionary(str) | — | | |
| 34 | wind_dir_deg | 风向 | float | 度 | | VRB 为 NaN |
| 35 | wind_dir_q | 风向质量码 | dictionary(str) | — | | |
| 36 | wind_speed_kts | 风速 | float | 节 knots | 缺失 0.113%（7,988） | |
| 37 | wind_speed_q | 风速质量码 | dictionary(str) | — | | |
| 38 | vis_m | 能见度 | float | 米 | 缺失 0.025%（1,747） | 码值直接=米 |
| 39 | vis_q | 能见度质量码 | dictionary(str) | — | | |
| 40 | precip_mm | 降水量 | float | 毫米 mm | 缺失 9.025%（636,750） | |
| 41 | precip_q | 降水质量码 | dictionary(str) | — | AA1 整段缺失时为空 | |
| 42 | precip_period_h | 降水累计时段 | float | 小时 | 随 AA1 | |
| 43 | precip_reported | 降水是否有报告 | double(0/1) | — | matched 子集：1=6,418,994；0=636,167 | **0=缺测≠无雨**；0 行 `precip_mm` 必为空 |

> 质量码含义（ISD）：`5`=通过全部质量控制（最可靠），`1`=通过粗范围检查；`9`=缺测；`A/C/P/U/I/2/6/7` 等为估计、未通过某层检查或特殊状态，做模型前应结合数值列是否缺失一并判断。全量质量码未逐条人工复核，分布见 `data/integrated/fusion_stats.json` 的 `quality_code_dist_in_matched`。
> 观测去重：NOAA 清洗表 3,905,968 行 → 融合前按 `(station_id, obs_utc)` 去重（同时刻 FM-15 优先）→ 3,898,753 行（移除 7,215 条重复时刻）。

---

## 附：关键文件

- `data/cleaned/bts_flights_2024.parquet`、`data/cleaned/noaa_obs_2024.parquet`
- `data/cleaned/airport_timezones.csv`、`data/cleaned/airport_state_check.csv`
- `data/integrated/flights_weather_2024.parquet`、`data/integrated/flights_weather_2024_sample.csv`
- 统计：`data/cleaned/bts_clean_stats.json`、`data/cleaned/noaa_clean_stats.json`、`data/cleaned/airport_timezone_stats.json`、`data/integrated/fusion_stats.json`
