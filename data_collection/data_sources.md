# 美国航班延误分析数据来源与采集记录

项目：基于多源数据融合的美国航班延误时空特征及天气关联分析  
责任模块：成员1 数据采集与来源管理  
采集日期范围：2026年10月28日至29日（北京时间，Asia/Shanghai）  
本记录更新日期：2026年10月29日

## 一 范围与证据口径

本文件对应课程作业第三部分，记录四个独立来源的获取方式、采集时间、原始规模、数据类型、许可与使用说明、主要字段、跨源关联字段及必要的采集核验。仅描述数据采集、来源管理和机场—天气站映射准备，不宣称完成天气清洗、航班天气融合、统计分析、回归或聚类。

统计结果来自本项目实际运行脚本后返回的检查结果。文件级完整记录保存在项目的 JSON、CSV 与 JSONL 元数据及日志中，应与本文件一并提交。本文件是来源摘要，不替代346个站点及12个月航班的逐文件清单。

手动下载文件的日期由采集者确认为2026年10月28日至29日，目前只确认到该范围，未逐文件补造时分秒。批量脚本记录的时间使用UTC，`+00:00`表示UTC，换算北京时间应加8小时。`checked_at_utc`为检查时间，不是下载时间；ZIP内部修改时间、HTTP Last-Modified也不是本次采集时间。

## 二 数据源总清单

| 编号与角色 | 独立发布来源 | 获取方式与数据形态 | 本次范围与规模 | 采集时间 | 跨源关联字段 |
|---|---|---|---|---|---|
| S01 主要 | 美国交通统计局 BTS | 官方PREZIP月度ZIP，内含逐航班CSV；本地使用全年打包文件中的12个月度原始CSV | 2024全年；7,079,061条航班；CSV合计3,201,887,863字节 | 本项目获取日期范围为2026-10-28至29；上游官方文件获取时间见全年包内file_manifest.json，二者分别保留 | Origin、Dest、OriginAirportID、DestAirportID、FlightDate、CRSDepTime、OriginState、DestState |
| S02 主要 | NOAA／NCEI Global Hourly | 官方开放文件，按站点下载2024年CSV；配套ISD站点目录 | 正式346站；4,529,560条观测；CSV合计2,517,133,047字节；其中1站仅部分年份覆盖 | 手动试采集在2026-10-28至29；批量逐文件时间见noaa_download_manifest_2024.json及下载日志 | STATION、DATE；目录USAF、WBAN、ICAO、LAT、LON、BEGIN、END |
| S03 辅助 | OurAirports | 官方公开机场资料CSV快照 | 86,293条机场记录；12,751,638字节；iso_country为US的记录32,697条 | 手动采集日期范围2026-10-28至29 | ident、iata_code、icao_code、gps_code、latitude_deg、longitude_deg、iso_country、iso_region |
| S04 辅助 | 美国人口普查局 U.S. Census Bureau | 2024年1∶500,000州界ZIP；Shapefile、DBF、PRJ等 | 56个州及州级等同地区；ZIP为3,242,450字节 | 手动采集日期范围2026-10-28至29 | STATEFP、STUSPS、GEOID、边界几何及机场坐标 |

### 独立性与来源形态说明

BTS航班报送业务记录、NOAA气象观测产品、OurAirports社区机场资料和Census边界产品分别按独立底层数据产品计数。NOAA托管在开放存储地址，不另算一个来源；ISD站点目录及各个气象站文件仍属于NOAA来源。12个月的BTS文件也只算一个来源。BTS与NOAA虽同属美国联邦机构数据体系，但采集对象和底层数据产品不同，并非相互转载。

本项目具有逐航班业务表、气象站观测时间序列、机场参考表和地理空间矢量等形态。政府或机构开放数据、社区开放参考资料、地理空间数据的类别说明应与教师口径一致。**目前未取得教师对“至少3类来源／形态”的确认记录，不能仅凭4个机构或4个文件类型直接宣称该项已验收。**如教师将社区CSV与其他开放CSV归为同一类，小组需要确认类别解释或调整方案；本文件不虚构该项审批结果。

## 三 各来源获取与使用说明

### S01 BTS逐航班运行记录

- 数据集：Reporting Carrier On-Time Performance (1987-present)。
- [官方数据说明](https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ)。
- 官方月度下载模板：`https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2024_{month}.zip`，其中month为1至12，不补前导零。
- 本地获取文件：`data/raw/BTS/BTS_2024_full_year.zip`，并保留解压后的12个月度CSV。年度外层ZIP由AI助手汇集官方月度文件后打包，不是BTS另行发布的官方年度产品。包内CSV按原始字节保留，没有在打包过程中清洗、删行或拼接记录。
- 本地全年航班读取结果：2024年1月1日至12月31日，共7,079,061条，涉及348个机场代码与机场ID组合。
- 主要字段：FlightDate、Reporting_Airline、Origin、Dest、OriginAirportID、DestAirportID、OriginCityName、DestCityName、OriginState、DestState、CRSDepTime、ArrDelay、ArrDel15、Cancelled、Diverted、Distance。
- CSV尾部空字段等原始结构保留；本阶段不因字段暂不用于模型而改写原始文件。
- 使用说明：采用官方公开下载渠道，保留各月readme.html和来源署名。美国政府职务作品的一般公共领域规则可作为使用背景，但不据此给所有承运人报送内容或附属材料另行虚构一个CC许可；具体限制仍以产品及说明文件为准。

| 月份 | 实际读取记录数 |
|---|---:|
| 2024-01 | 547,271 |
| 2024-02 | 519,221 |
| 2024-03 | 591,767 |
| 2024-04 | 582,185 |
| 2024-05 | 609,743 |
| 2024-06 | 611,132 |
| 2024-07 | 634,613 |
| 2024-08 | 619,025 |
| 2024-09 | 582,622 |
| 2024-10 | 615,497 |
| 2024-11 | 575,404 |
| 2024-12 | 590,581 |
| 合计 | 7,079,061 |

全年包内`file_manifest.json`记录月度来源URL、官方ZIP字节数与校验值、CSV字节数与校验值及上游获取时间；`checksums.sha256`用于解压后CSV核验。先前单独获取的1月文件与全年包内1月数据不重复计数。

### S02 NOAA天气观测与站点目录

- [官方ISD产品说明](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)。
- 天气文件模板：`https://noaa-global-hourly-pds.s3.amazonaws.com/2024/{station_id}.csv`。
- [站点目录isd-history.csv](https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv)。
- [官方字段及质量码文档](https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf)。
- [官方服务迁移说明](https://www.nesdis.noaa.gov/news/service-location-change-integrated-surface-data-global-hourly)。本次采用其指定的开放存储地址读取2024年历史数据，不将ISD视为持续更新的实时产品。
- 保存位置：`data/raw/NOAA/2024/{station_id}.csv`及`data/raw/NOAA/isd-history.csv`。
- 站点目录共29,661条记录，13,439条的起止日期与2024年有交集；这不保证每个站点全年都有文件或每日都有观测。
- 站点ID按USAF与WBAN字符串拼接，保留前导零。历史目录和观测文件的站点编号用于交叉核验。
- 核心字段：STATION、DATE、NAME、REPORT_TYPE、LATITUDE、LONGITUDE、CALL_SIGN、QUALITY_CONTROL、WND、VIS、TMP、DEW、SLP及可用降水字段AA1等。各站可选字段不同，以实际表头为准。
- DATE按UTC解释。报告类型的原始空格保留；不把SOD、SOM等汇总报告当成逐次机场METAR观测。
- 本阶段只统计报告类型，不解析或填补气温、风、能见度和降水；后续必须按官方文档处理质量码、缺失码、倍率及降水累计时长。缺少降水记录不能当成无雨。
- 使用说明：经NOAA官方开放发布渠道获取并标注NOAA/NCEI来源；保留原始产品说明，不能把加工结果呈现为官方原始产品，不声称获得官方认可。ISD整合多种原始观测来源，不额外推定全球全部原始贡献数据具有同一独立许可。

试采集30站共234,614,706字节、398,675条观测、309,838条FM-15/FM-16记录，基本检查未发现异常。30站中包括SGU试采集候选。

正式清单排除SGU与XWA，包含346个机场和346个唯一站点。正式下载运行新下载317个站点，复用29个已核验文件；失败0、未完成0。随后本地逐行检查346个正式文件，统计如下：

| 项目 | 结果 |
|---|---:|
| 正式天气文件数 | 346 |
| CSV字节数 | 2,517,133,047 |
| 全部观测记录 | 4,529,560 |
| FM-15/FM-16记录 | 3,905,968 |
| 通过本次基本检查的站点 | 345 |
| 有部分年份覆盖的站点 | 1 |

基本检查包括记录数、站点编号、日期可解析性、是否属于2024年、月份存在性及是否有FM-15/FM-16报告。通过这些检查不等于逐日逐小时完整、字段质量合格或最终天气匹配成功。

SGU文件另外保留为试采集材料，未计入上述正式346站体积和记录数。最初30站中其余29站已被正式数据包含，试采集体积不能再次加到正式数据总量中。

### S03 OurAirports机场参考资料

- [官方来源及使用条款](https://ourairports.com/data/)。
- [下载airports.csv](https://ourairports.com/data/airports.csv)。
- [字段字典](https://ourairports.com/help/data-dictionary.html)。
- 本地路径：`data/raw/OurAirports/airports.csv`。
- 本次快照86,293条；US记录32,697条。US记录数量不是本项目实际有航班的机场数量，最终机场范围由BTS全年清单确定。
- 使用说明：官方明确将数据发布至Public Domain，并不保证准确性或适用性。本项目仍保留来源和下载快照校验值。
- 主要字段：id、ident、type、name、iata_code、icao_code、gps_code、local_code、keywords、latitude_deg、longitude_deg、iso_country、iso_region。
- 关联用途：优先用机场代码核对实体，再获取坐标、参考标识与州级地区信息。BTS的AirportID与OurAirports的id不是同一个编号体系，不能直接数值连接。
- 当前快照不是2024年历史快照，机场名称或代码变化必须单独核验；不得用当前名称覆盖历史业务代码而不留记录。该表也不默认提供机场时区。

### S04 Census州界

- [官方2024年边界产品页面](https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html)。
- [直接下载cb_2024_us_state_500k.zip](https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip)。
- 本地路径：`data/raw/Census/cb_2024_us_state_500k.zip`。
- 数据为2024年州及州级等同地区的1∶500,000制图简化边界，500k是比例尺而非文件大小。
- ZIP CRC检查通过，56条有效属性记录、0条删除标记、56条SHX索引；必要关联字段检查通过。几何类型编号5，即Polygon。
- 关联字段：STATEFP、STUSPS、GEOID、NAME和边界几何。州代码作为字符串处理并保留前导零。
- 使用说明：Census公开地理产品，按官方产品及说明使用并注明年份、比例尺与来源；一般政府作品使用背景见文末参考，不虚构CC BY或其他未核实的独立许可。
- PRJ确认地理坐标系NAD83，角度单位为度，GRS 1980椭球。后续空间关联须确认并转换相关图层坐标系，不能仅因同为经纬度就默认与WGS84完全一致。

```text
GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",SPHEROID["GRS_1980",6378137,298.257222101]],PRIMEM["Greenwich",0],UNIT["Degree",0.017453292519943295]]
```

56条不是56个美国州。简化边界、岛屿、离岸机场及地区代码的异常应交由后续空间核验处理，不能在本阶段无记录删除。

## 四 原始规模与来源占比

采用十进制单位：1 MB＝1,000,000字节，1 GB＝1,000,000,000字节。

为避免压缩口径混用，主要来源使用本地解压或直接发布的原始CSV字节数：

| 主要来源 | 原始CSV字节数 | 十进制GB | 两个主要来源内占比 |
|---|---:|---:|---:|
| BTS | 3,201,887,863 | 3.202 | 55.99% |
| NOAA正式346站 | 2,517,133,047 | 2.517 | 44.01% |
| 合计 | 5,719,020,910 | 5.719 | 100.00% |

两个主要来源的文件体积合计已超过2GB，分别超过200MB，且文件体积占比均低于80%。此为已下载原始文件的工程统计，不是清洗后样本量或教师对有效规模口径的最终认定。

OurAirports与Census为小规模辅助来源，不依靠其体积达到2GB要求。Census目前确认的是ZIP体积，未将其与解压后的主体数据混算到上述表中。NOAA站点目录、README、元数据、日志、重复的1月文件、年度ZIP及其解压CSV副本不重复计量。30站试采集文件也不作为正式346站之外的新增数据重复累计。

所有正式天气站均来自BTS全年机场范围的映射，不通过下载无关站点、不同年份或重复文件凑量。原始CSV包含多种报告类型及质量字段，最终主关联优先FM-15/FM-16；若课程对“有效规模”要求仅计入最终选用报告或字段，应另行按同一口径重新核算，不能直接把原始文件统计视为已经完成全部质量验收。

## 五 机场天气站映射及覆盖例外

### 映射准备方法

从BTS全年提取348个机场代码与机场ID组合。通过OurAirports核对机场身份，优先按iata_code匹配；对没有直接匹配的记录生成历史标识候选并保留证据。对NOAA目录，仅考虑起止日期与2024年有交集且坐标有效的站点。

初筛保存机场25公里内的全部候选，优先代码一致，其次目录日期覆盖全年，再比较球面距离。自动通过规则要求：唯一机场匹配、唯一代码一致的站点候选、距离不超过10公里、目录起止日期覆盖全年。目录覆盖全年仍不保证实际观测文件全年完整。

原始映射结果345条通过自动规则、2条站点待复核、1条无站点。修订表保留原status和reason，另加采集状态及证据，不覆盖初始判定。正式范围为345条自动规则记录加PBI一条历史代码交叉核对记录，共346个机场／站点。

| 机场或站点 | 本次发现 | 处理与状态 |
|---|---|---|
| PBI／72203012844 | 当前机场快照的历史标识候选；目录及天气文件名称为West Palm Beach；目录距离约0.393公里；样本覆盖2024年12个月 | historical_alias_crosschecked；保留2024业务代码、历史标识依据和当前快照差异，纳入正式采集。该状态不等于天气字段已清洗或已完成人工逐条核验 |
| SGU／72475423186 | 目录距离10.647公里；2024天气文件坐标仍为37.1、-113.6；NWS历史通知记录过KSGU站点位置变化 | trial_only_location_conflict；保留试采集文件及原坐标、原距离，不纳入正式346站；在进一步核实前不能改为零距离或直接用于正式天气关联 |
| XWA | 在当前目录、年份与25公里规则下未找到候选 | unmatched_retained；保留机场及航班，不以旧ISN机场站点直接代替，不宣称XWA实际没有天气观测 |
| WYS候选／72676494163 | 正式文件为WEST YELLOWSTONE；只有2024-04-29 14:20至2024-11-06 06:59 UTC；1、2、3、12月无记录，4月和11月也仅部分覆盖 | 保留原始文件，登记部分时间覆盖；原因未核验，不能直接断定季节停运或下载错误；后续范围外天气保持未匹配，不补造天气 |

West Yellowstone文件共13,427条，其中FM-15为13,357条；文件大小5,822,764字节。站点编号不一致、日期无法解析和非2024记录均为0。该文件未从正式来源统计中删除，但其覆盖不足已明确披露。

相关依据：

- [NWS KSGU历史站点位置调整通知](https://www.weather.gov/media/notification/tins/tin14-29nam_aaa.pdf)。
- [FAA关于旧ISN关闭及新XWA启用的公告](https://www.govinfo.gov/content/pkg/FR-2019-08-29/pdf/2019-18577.pdf)。
- NOAA原始站点目录、2024年PBI和SGU文件及本地检查记录。

### 提供给成员2的关联接口

- 实体：BTS机场代码／AirportID → OurAirports机场标识 → NOAA站点ID。保留全部未匹配和例外。
- 时间：BTS的FlightDate和CRSDepTime为计划当地起飞日期时间；后续核对机场时区并转UTC，再关联NOAA DATE。采集阶段尚未完成此关联。
- 项目初始天气匹配规则：计划起飞前最近一条FM-15或FM-16，不超过90分钟；60分钟窗口作为后续敏感性检查。此为约定，不是本阶段已执行结果。
- 空间：机场坐标与Census边界、STUSPS或GEOID关联。州界不是仅用于地图装饰；坐标系、领地和代码异常需核验。
- WYS不完整覆盖、SGU位置冲突与XWA未匹配须随数据交接；不存在天气记录不能填为晴天、无雨或零风速。

## 六 日志元数据与校验信息

### 逐文件证据位置

所有路径相对于`flight_delay_project`根目录。BTS全年包通常解压到BTS目录下的子文件夹，以下“全年包解压目录”以本机实际位置为准，不要求复制同一份CSV到第二个目录。

| 文件或位置 | 记录内容 |
|---|---|
| BTS全年包解压目录/file_manifest.json | 各月官方来源URL、上游获取时间、ZIP与CSV规模及SHA-256 |
| BTS全年包解压目录/checksums.sha256 | 解压后12个月CSV校验值；本地检查12/12通过 |
| BTS全年包解压目录/download_log.jsonl | 全年打包数据对应的上游官方文件采集日志，不冒称为本机浏览器下载日志 |
| metadata/ourairports_inventory.json | 机场快照记录数、US记录数、字节数、字段、SHA-256与检查时间 |
| metadata/noaa_station_directory_inventory.json | 站点目录规模、与2024年相交记录数、字节数及SHA-256 |
| metadata/bts_airports_2024.csv | 从全年航班提取的348个机场身份组合及出发／到达数量 |
| metadata/airport_station_mapping.csv | 初始逐机场映射及原始判定依据 |
| metadata/airport_station_candidates.csv | 25公里内候选站点、距离、代码一致性和排序依据 |
| metadata/airport_station_review.csv | 初始3条需复核记录；保留历史，不将其误认为最新状态 |
| metadata/airport_station_mapping_reviewed.csv | 全348条记录的修订采集状态与例外依据 |
| metadata/noaa_trial_airports_30.csv | 30机场试采集清单 |
| metadata/noaa_pilot_inventory.json | 最初PBI、SGU两个手动样本的检查记录 |
| metadata/noaa_trial_inventory_30.json | 30站试采集逐文件检查记录 |
| metadata/noaa_full_airports_2024.csv | 正式346机场及站点采集范围 |
| metadata/noaa_download_manifest_2024.json | 正式及已记录试采集文件的URL、实际批量获取时间、字节数、SHA-256、HTTP信息与核验状态 |
| logs/noaa_download_log.jsonl | 下载开始、失败尝试、重试、成功及已有文件核验事件 |
| metadata/noaa_full_inventory_2024.json | 正式346站逐文件时间范围、月份、报告类型、位置及基本异常检查 |
| metadata/census_state_inventory.json | ZIP校验、成员文件规模、DBF字段、记录数、索引数、PRJ和SHA-256 |
| metadata/census_states_2024.csv | 56条STATEFP、STUSPS、NAME和GEOID参考记录 |

下载脚本核对Content-Length（服务器提供时）、必要CSV字段及首条站点编号，并计算SHA-256；检查脚本随后扫描全部记录核对日期及站点。原始HTTP ETag不当作SHA-256使用。已有文件只有与已知字节数和校验值相符才跳过；不能以“文件存在”代替下载成功。

天气检查JSON中`downloaded_at: null`不表示没有下载，也不能用检查时间填充。自动下载时间从下载manifest和日志关联回填；手动文件使用本文件声明的2026-10-28至29日期范围，并标注日期精度。

### 已明确核验的代表性SHA-256

| 文件 | SHA-256 |
|---|---|
| OurAirports airports.csv | `9c1f3295b59f84c475f8c8555fa102505d7b4af0f931002cc5558dfeee1e43aa` |
| Census cb_2024_us_state_500k.zip | `3e81cbb6cf5f60d9b01ef3e730afa14d61ce5f784252a0b33a696135e71447bc` |
| NOAA 72676494163.csv | `d9f97bcf12d8ad6444cebfca617030fff7ce2861f7e0d4bfb2eefc7b27673dd6` |

其他每月、每站校验值按上表的完整文件清单提交，不在此伪造未展示的哈希。OurAirports会更新，未来重新下载的快照可能与本次哈希不同；不能为迎合旧哈希修改新数据。

## 七 采集工程与复现

环境：Windows，Python 3.11.9。已运行脚本采用Python标准库；采集无须安装requests、pandas或地理处理库。

正式NOAA下载并行数为2，流式写入`.part`，基本检查通过后才改为正式CSV；按站点最多尝试3次，记录失败并对401、403、404停止盲目重试。中断后重新运行会核验并复用已登记的成功文件；未完成的单个文件重新下载，不宣称支持HTTP断点续传。不得同时运行新旧下载脚本写入同一目录。

| 本地crawler脚本 | 功能 |
|---|---|
| check_bts.py | 核对全年CSV大小与SHA-256 |
| check_airports.py | 核对机场资料字段、记录数并保存元数据 |
| prepare_airports.py | 检查站点目录，逐月读取航班并提取机场身份清单 |
| build_airport_station_mapping.py | 建立初始映射、候选表与复核清单 |
| check_weather_pilot.py | 当前已扩展为按正式清单检查346站，输出noaa_full_inventory_2024.json；早期两站及30站结果另外保留 |
| prepare_noaa_trial.py | 保留例外并生成30机场试采集清单 |
| download_noaa_trial.py | 首批天气下载及日志 |
| prepare_noaa_full.py | 生成正式346站采集清单 |
| download_noaa_full.py | 正式两并发天气下载，核验已有文件并记录日志 |
| check_census.py | CRC、DBF、SHX、PRJ及基本文件结构检查 |

本表列出本次已指导保存并使用的脚本，不虚构脚本已上传GitHub。实际交付时将本机对应文件放入仓库，保留真实代码及运行记录。公开文件可以按各节URL重采集；BTS官方月度获取与三个手动辅助文件的自动下载代码见附录示例。附录代码为复采补充，未冒称已在采集者电脑运行。

## 八 本模块交付与后续边界

成员1交付本文件、原始数据或可重建索引、crawler采集与检查代码、下载日志、逐文件清单与校验值、机场—天气站映射和例外记录。按课程要求，GitHub不必上传约5.7GB完整主数据；应保留可运行代码、代表性样本、元数据、完整文件摘要与校验值。仅提交本Markdown而缺少它引用的本地清单和代码，不等于交付了成员1全部成果。

本次已经核验下载与基本结构，尚未核验天气变量质量码、实际时间匹配率、时区转换、空间关联率、TT等地区代码和所有手工实体例外。后续清洗、融合、分析与可视化属于其他成员，不在本模块伪造结果。

代表性样本应另从原始文件按明确规则提取并注明抽样方式，不能将样本算作额外来源或增加有效规模。当前文档不宣称已经在本机运行独立样本导出或完成GitHub上传。

## 九 AI使用说明 供并入小组AI_USAGE.md

使用工具：ChatGPT；时间范围为2026年10月28日至29日。未单独确认具体底层模型版本，不虚构版本号。

AI参与课程要求解读、官方来源定位、全年航班文件整理、标准库脚本编写、字段与时间口径说明、映射规则设计、异常解释和本来源文档整理。采集者在本地运行代码并返回实际输出，文档据这些结果填写。原始文件来自公开数据渠道，不由AI合成。

代表性指令：只完成成员1的数据采集与来源管理，按课程第三部分要求形成独立Markdown来源清单；改为逐步指导本地采集；批量下载并保留日志、哈希和机场—天气站对应关系。

采纳了按月／站点组织原始文件、保留SHA-256和分层映射的方案。根据运行结果将单月试采集扩展到全年，将两站和30站试采集扩展到正式346站。为改善串行下载等待，改为两并发和进度输出。对SGU没有采纳“代码一致即可确认位置”的简化判断，对XWA没有用旧机场站点补配。

核验包括ZIP CRC、文件长度、SHA-256、逐月实际航班计数、站点编号与日期扫描、天气报告类型统计、州界DBF／SHX结构检查和PRJ读取。手动下载日期仅记到确认范围；未完成的人工复核不写成已完成。

反思：只看目录BEGIN／END或月份齐全会高估覆盖，WYS实际仅覆盖部分年份；当前机场快照不能直接代表2024属性；四个独立来源也不自动满足三类形态。AI提高了代码编写和排错效率，但每个统计与映射状态仍需通过真实文件或运行输出核实。小组另需汇总其他成员阶段及个人学习反思，本节不代替全组完整AI_USAGE.md。

## 十 参考与许可依据

1. [BTS数据表说明](https://www.transtats.bts.gov/TableInfo.asp?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ)。
2. [NOAA ISD产品及字段文档入口](https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database)。
3. [OurAirports来源与Public Domain条款](https://ourairports.com/data/)。
4. [OurAirports字段字典](https://ourairports.com/help/data-dictionary.html)。
5. [Census 2024边界产品](https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html)。
6. [美国政府开放数据许可说明](https://resources.data.gov/open-licenses/)。该一般说明不替代具体产品中的第三方或特殊限制。

## 附录 公开文件复采代码示例

以下示例用于补齐官方BTS月度文件和手动参考文件的复采途径，不会与现有数据混在一个目录。将代码保存为`crawler/download_public_sources.py`并运行时，数据写入`data/recaptured`，逐次日志写入`logs/public_recapture_log.jsonl`。它会获取运行当时的公开快照，不保证动态机场资料与本次快照逐字节一致；原始本次文件和manifest仍需保存。本示例尚未在采集者电脑执行，不能当作本次已有采集日志。

```python
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import time
import urllib.request
import zipfile

project = Path(__file__).resolve().parent.parent
(project / "logs").mkdir(parents=True, exist_ok=True)
log_path = project / "logs/public_recapture_log.jsonl"

tasks = [
    ("OurAirports/airports.csv", "https://ourairports.com/data/airports.csv"),
    ("NOAA/isd-history.csv", "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"),
    ("Census/cb_2024_us_state_500k.zip",
     "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip")
]
for month in range(1, 13):
    name = f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2024_{month}.zip"
    tasks.append((f"BTS/{name}", "https://transtats.bts.gov/PREZIP/" + name))

for relative, url in tasks:
    destination = project / "data/recaptured" / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print("已存在，保留；如需复核请读取既有日志：", destination)
        continue
    temporary = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, 4):
        record = {"url": url, "path": str(destination), "attempt": attempt,
                  "started_at_utc": datetime.now(timezone.utc).isoformat()}
        succeeded = False
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "UniversityCourseResearch/1.0"})
            with urllib.request.urlopen(request, timeout=90) as response:
                expected = response.headers.get("Content-Length")
                with temporary.open("wb") as f:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        f.write(block)
            acquired = datetime.now(timezone.utc).isoformat()
            if expected and temporary.stat().st_size != int(expected):
                raise ValueError("Content-Length不一致")
            if destination.suffix == ".zip":
                with zipfile.ZipFile(temporary) as z:
                    if z.testzip() is not None:
                        raise ValueError("ZIP CRC检查失败")
            else:
                import csv
                with temporary.open(encoding="utf-8-sig", newline="") as f:
                    if len(next(csv.reader(f))) < 2:
                        raise ValueError("不是预期CSV")
            with temporary.open("rb") as f:
                checksum = hashlib.file_digest(f, "sha256").hexdigest()
            size = temporary.stat().st_size
            temporary.replace(destination)
            record.update(status="success", acquired_at_utc=acquired,
                          bytes=size, sha256=checksum)
            succeeded = True
        except Exception as error:
            record.update(status="failed_attempt", error=f"{type(error).__name__}: {error}")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(record["status"], relative)
        if succeeded:
            break
        if attempt < 3:
            time.sleep(2 ** attempt)
    time.sleep(1)
```
