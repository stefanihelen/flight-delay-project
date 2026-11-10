# 成员1数据采集模块运行说明

本说明供组长并入全组README。补充范围是代表性原始样本、抽样说明和采集模块复现步骤，不包含清洗数据、融合表、最终多源关联图或模型结果。

## 一 当前状态与本次需要做的事

此前已交付四类原始来源、采集与检查代码、metadata、NOAA日志和data_sources.md。按采集者返回的实际运行结果，BTS全年7,079,061条、原始CSV约3.202GB；NOAA正式346站4,529,560条、原始CSV约2.517GB。组长在本机核验BTS的12个月CSV大小与SHA-256通过。以上不是本补充包重新运行全量数据得出的新结论。

**本项目已完成真实样本导出，样本位于 data/samples/raw/member1/，包含3,112条航班记录和733条天气记录，并附有抽样说明、来源追溯和校验信息。实际结果见该目录的 README.md 和 sample_manifest.json。** 补充脚本已做隔离测试，不把测试用临时数据当作课程数据，也未重新下载数据。脚本不会联网、覆盖原始文件、修改历史日志或重新计算航班天气融合表。

将本包内的crawler目录合并到原项目crawler；将本说明、RUN_MEMBER1_SUPPLEMENT.bat及docs内补充说明放到原项目对应位置。不需要替换原有采集脚本或data_sources.md。补充包使用新文件名；已有同名补充脚本应先备份再更新，`_member1_common.py`须与两个补充脚本放在同一个crawler目录。

## 二 环境与目录

实际采集环境为Windows、Python 3.11.9。现有与新增采集脚本仅使用Python标准库，无须安装pandas、requests或地理处理库。早期弹窗脚本使用tkinter，需要正常的Python桌面安装；本次新增的样本与体积脚本不需要弹窗，也不依赖Windows通常缺省没有的IANA时区包。

在项目根目录运行命令；不将个人盘符或姓名写死在代码中。目录用途：

| 相对路径 | 内容 |
|---|---|
| data/raw/BTS/ | 全年ZIP及唯一一套解压后的12个月CSV、file_manifest.json、checksums.sha256等；允许全年包解压为子目录 |
| data/raw/NOAA/isd-history.csv | 原始ISD站点目录 |
| data/raw/NOAA/2024/ | 正式天气CSV和另存的SGU试采集文件 |
| data/raw/OurAirports/airports.csv | 本次机场参考快照 |
| data/raw/Census/cb_2024_us_state_500k.zip | 完整州界ZIP，包含配套SHP、SHX、DBF、PRJ等 |
| crawler/ | 采集、检查、映射与本次补充脚本 |
| metadata/ | 各来源inventory、正式与试采集清单、机场映射及逐文件manifest |
| logs/ | NOAA等实际下载日志 |
| data/samples/raw/member1/ | 本次脚本成功运行后生成的样本、清单、哈希及自动抽样说明 |

若BTS目录下有两套都带manifest和完整CSV的解压副本，新脚本会拒绝选择，以免误用版本或重复计算。将不用的副本移动到项目数据目录之外即可，不需要删除正式原始文件。不能把额外下载的1月CSV再次算入全年数据。

## 三 现在补齐两项材料的最短步骤

1. 将补充包内容放入原flight_delay_project，保留原有data、metadata和logs。
2. 在项目根目录双击`RUN_MEMBER1_SUPPLEMENT.bat`；或在根目录的命令提示符依次运行：

```bat
python crawler\audit_source_sizes.py
python crawler\export_raw_samples.py
```

3. 第一个脚本从BTS的file_manifest.json读取逐月体积，核对summary及12个本地CSV大小；再读取正式NOAA清单和inventory核对文件大小。输出`metadata/source_size_audit.json`。不使用固定的3,201,887,863字节常量，不以346等固定数代替当前清单；不重新下载或扫描全年航班。
4. 第二个脚本验证所需来源文件及已知哈希，流式扫描1月、7月的月度CSV及三个站点全年天气。导出样本后重新读取样本CSV并核对导出哈希，输出`data/samples/raw/member1/`和`metadata/member1_sample_export_receipt.json`。仅扫描所选两个月，不将全年航班一次性读入内存。扫描来源文件需要等待，程序逐月及逐站显示进度。
5. 看到“成员1样本导出完成”后，查看样本目录的README.md及sample_manifest.json。实际条数、范围、原始标签自然分布、来源版本和哈希均以本机结果为准。
6. 将`data/samples/raw/member1/`、本README、新增crawler脚本、docs补充说明及新增两个metadata JSON交给组长。原始大数据不需要重新发一遍。组长将采集运行说明并入全组README，并将小样本加入仓库；不要把临时测试数据或约5.7GB原始数据全部上传GitHub。

脚本默认不覆盖已有样本目录。若需要重新导出，先将整个`data/samples/raw/member1`移动到备份位置，再运行；不要只删其中一个文件。若导出失败，脚本清理自己新建的临时目录，不出具成功回执；原始data/raw不变。

## 四 样本选取规则

### 航班

固定选择出发机场JFK、ORD、LAX，以及当地航班日期2024-01-09和2024-07-09，保留范围内全部原始记录。两个日期分属冬季和夏季，三个机场供不同地区的读取与关联测试；不声称在统计上代表全年机场、航班量或天气分布。

不随机抽样，不需要随机种子；不按延误、取消结果筛选，不修改标签凑齐类别。Cancelled、Diverted、ArrDel15等原始字段及所有其他字段照原值保留，程序仅汇总自然出现的类别以便验收。若未覆盖全部类别，说明里会如实提示，不补造记录。样本CSV保留原字段顺序、值及选中记录顺序，但经过CSV重新序列化，不宣称与原文件文本片段逐字节一致。源文件和导出文件分别计算SHA-256。

### 对应天气与跨日边界

从`metadata/noaa_full_airports_2024.csv`获取所选机场的正式站点，不臆造站点编号。对每个当地航班日期D，保留天气UTC范围`[D-1日00:00, D+2日00:00)`：

| 当地航班日期 | 保留天气UTC起点（包含） | 保留天气UTC终点（不包含） |
|---|---|---|
| 2024-01-09 | 2024-01-08 00:00 | 2024-01-11 00:00 |
| 2024-07-09 | 2024-07-08 00:00 | 2024-07-11 00:00 |

这是针对所选美国本土机场的保守UTC包络；其范围足以包含计划当地时间转换UTC后的跨日、2400次日及90分钟前序观测。**该脚本并未逐班转换时区，也未执行90分钟天气匹配，不是融合代码。**宽窗口中可能包含本次航班不使用的天气记录，这是便于后续关联测试的上下文，不计入新增有效体积。

保留窗口内全部原报告类型及天气原字段，不在采集补充中清洗质量码或把日/月汇总报告当作METAR。脚本核对每个机场对应的两个窗口都有FM-15/FM-16，输出逐窗口实际条数。存在观测不保证每班都可在90分钟内匹配，成员2仍需处理时区、重复观测、匹配间隔、质量码和缺失。

### 辅助原始文件

OurAirports的完整airports.csv和Census完整ZIP按字节复制，复制前核对原有inventory哈希，复制后再次核对。保留Census ZIP可同时保留全部配套地理文件；如需解压提交，必须一起保留SHP、SHX、DBF、PRJ等，不能只交SHP。机场快照不冒称为2024历史属性，Census原坐标系为NAD83。

### 输出与验收

| 样本目录内文件 | 内容与判定 |
|---|---|
| BTS/bts_flights_sample.csv | 六个机场／日期组合的全部选中原始航班，实际条数运行后统计 |
| BTS/flight_sample_lineage.csv | 样本数据行号对应原CSV文件及逻辑记录号，不把逻辑记录号误称为文本物理行号 |
| NOAA/站点编号.csv | 对应三个站点、两个保守UTC窗口内的全部原始观测 |
| OurAirports/airports.csv | 完整原始快照，复制前后哈希一致 |
| Census/cb_2024_us_state_500k.zip | 完整原始州界包，复制前后哈希一致 |
| airport_station_sample_mapping.csv | 从正式清单原样选出的三个机场映射，不改写全量映射 |
| sample_manifest.json | 真实来源路径、源哈希、版本标识、机场／日期、选取规则、实际条数、天气窗口、标签计数和限制 |
| checksums.sha256 | 导出CSV、映射及辅助文件的实际校验值 |
| README.md | 自动生成的实际抽样范围、条数及“仅用于展示与测试”说明 |

样本只用于展示、格式读取和后续关联测试，不替代正式分析，不算新增来源或额外原始规模。两个月原始航班及三站天气在导出前核对原SHA和读取记录数；正式样本写入新目录后不再与data/raw混算。

## 五 已完成采集的真实顺序与复跑接口

以下说明对应此前保存的脚本；补充包不重新提供或覆盖原团队已经收到的这些脚本。某些脚本的早期版本后经编辑扩充，须以当前实际保存的版本为准，不同时启动多个下载器写相同目录。

### 1 获取四类公开文件

| 来源 | 获取位置与本地准备 |
|---|---|
| BTS | `https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_2024_{month}.zip`，month为1—12；当前使用AI助手汇集的全年ZIP，解压后保留12份CSV及原manifest、说明、日志与校验值 |
| NOAA站点目录 | `https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv`，保存至data/raw/NOAA/ |
| OurAirports | `https://ourairports.com/data/airports.csv`，保存至data/raw/OurAirports/ |
| Census | `https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_500k.zip`，保存至data/raw/Census/ |
| NOAA年度天气 | `https://noaa-global-hourly-pds.s3.amazonaws.com/2024/{station_id}.csv`，按映射清单下载至data/raw/NOAA/2024/ |

上述文件是官方开放下载，不需要登录，不绕过网站限制。BTS全年外层ZIP是汇集打包件，不是官方单独年度产品。原始获取时间、检查时间和年度包打包时间分别保留。

### 2 检查来源及建立映射

| 顺序与命令 | 输入与操作 | 主要输出／判定 |
|---|---|---|
| `python crawler/check_bts.py` | 弹窗选择直接含12个CSV与file_manifest.json的目录，不选仅放年度ZIP的上层目录 | 大小与SHA核验应为12/12；清单记录数不是该脚本重新数行结果 |
| `python crawler/check_airports.py` | 弹窗选择本次airports.csv | metadata/ourairports_inventory.json；字段、记录数、体积和SHA |
| `python crawler/prepare_airports.py` | 先检查固定路径的isd-history.csv，再在弹窗选择全年BTS CSV目录 | 站点目录inventory及bts_airports_2024.csv；本次全量读取7,079,061条、348个机场组合 |
| `python crawler/build_airport_station_mapping.py` | BTS机场清单、OurAirports、ISD目录 | 原始mapping、候选表、复核表；原始345条自动规则、3条待核对 |
| 人工查看候选与证据 | PBI历史代码、SGU位置差异、XWA无当前候选 | 保留例外，不强制全匹配；人工需理解并复核代码输出 |
| 两站试采集与检查 | 最初浏览器下载PBI和SGU全年文件；旧版check_weather_pilot.py读取两站 | noaa_pilot_inventory.json；原始样本检查，非融合结果 |
| `python crawler/prepare_noaa_trial.py` | 映射表及最初两站inventory | reviewed映射及30站试采集清单；保留初始status与reason |
| `python crawler/download_noaa_trial.py` | 30站清单及已核验文件 | 下载manifest及日志；当时新下载28、复用2 |
| 30站天气检查 | 当时将check_weather_pilot.py的plan改为noaa_trial_airports_30.csv，输出改为noaa_trial_inventory_30.json | 30站逐文件覆盖与类型检查；此早期输出仍保留，不当作正式清单 |
| `python crawler/prepare_noaa_full.py` | 修订映射 | 正式346机场／站点，SGU候选与XWA未匹配排除在正式清单之外 |
| `python crawler/download_noaa_full.py` | 正式清单 | 两并发，流式下载、重试、实时进度、哈希和日志；当时新下载317、复用29，失败0 |
| `python crawler/check_weather_pilot.py` | **当前版本已改成正式noaa_full_airports_2024.csv，输出noaa_full_inventory_2024.json** | 346站逐行检查；记录WYS部分年份覆盖。名称虽含pilot，当前读取的是正式清单 |
| `python crawler/check_census.py` | 固定路径州界ZIP | CRC、属性字段、记录数、索引数与坐标系；56条、Polygon、NAD83 |
| `python crawler/audit_source_sizes.py` | BTS原manifest及当前正式NOAA inventory／文件 | 动态规模与占比，替代旧检查脚本末尾固定BTS体积的汇总用途 |
| `python crawler/export_raw_samples.py` | 已核验来源、正式映射与manifest | 本次新增代表性原始样本及自动说明，须实际运行后才有条数 |

注意最初的两站inventory是prepare_noaa_trial.py的依赖。若从已有项目复跑，保留该历史文件即可；当前check_weather_pilot.py已改为正式版，不会自动重建旧两站结果。不要把旧版试采集步骤、当前正式版脚本和不同输出名混淆。

### 3 规模汇总的改进

原check_weather_pilot.py末尾曾使用固定BTS字节数。本次新增audit_source_sizes.py从BTS原file_manifest.json的12个月记录求和，核对summary与本地文件大小，再对正式NOAA清单去重计量。生成source_size_audit.json，建议全组最终报告读取这个文件或用同样方式核算。

无需强行覆盖旧脚本。若组长希望直接改旧汇总代码，可在旧脚本中引入：

```python
from _member1_common import bts_size_audit
bts_manifest_path, bts_manifest, bts_bytes = bts_size_audit(project)
```

这段替代原`bts_bytes = 固定数字`，其他汇总逻辑不变；`_member1_common.py`须在同一个crawler目录。本次包已通过独立动态脚本消除汇总对常量的依赖，不冒称已修改组长本地旧文件。动态核算只确认文件体积，不替代SHA、有效字段口径或质量核验。

### 4 公开文件复采示例的测试状态

本包`crawler/download_public_sources.py`从已交付data_sources.md附录独立保存，逻辑未改，便于交付采集代码。已完成语法检查，**没有在本次补充中对公网执行，也没有在采集者电脑重新运行**；不能写成新的已执行采集过程。

它只在明确需要复采时运行，输出到`data/recaptured`并另写日志，保留当前data/raw原文件。它下载BTS月度ZIP和三个参考文件，不构建当前全年包的manifest，也不自动覆盖或切换正式版本。将复采文件接入新的处理流程前，需要人工核对新快照、解压月度ZIP、建立相应新版本清单并调整目录，不能把旧获取时间和旧哈希冒充为新采集证据。当前作业补样本无需运行它；已交付原项目数据与清单足以执行本节第三部分的复跑和样本重建。

## 六 已知异常和完成判定

- PBI：历史代码交叉核对后纳入正式采集，保留旧业务代码与当前快照差异。
- SGU：位置资料冲突，保留试采集文件，未计入正式346站；不能将目录距离改为零或无说明当作已确认。
- XWA：当前规则下未匹配，保留航班，不直接替代为旧ISN机场。
- West Yellowstone／72676494163：2024-04-29至11-06部分年份覆盖；1、2、3、12月无记录，4、11月也不完整；不是未经核验认定的季节停运或下载错误。
- 站点目录BEGIN／END或12个月均有记录不保证逐日逐小时完整；CSV基本检查通过不代表天气字段质量合格。
- NOAA manifest中的下载时间与inventory的检查时间不同；手动文件采集日期按已确认2026-10-28至29范围记录，不补造秒级时间。
- 原始文件体积主来源合计约5.719GB；有效规模、三类来源口径及最终融合质量仍由全组核验，不因本补充包而宣称额外通过。

下载完成看计划、新下载、复用、失败及未完成数；日志和manifest中应有对应记录。检查异常站点保留原因，不无记录删除。样本完成看导出回执与样本README／manifest，不用本补充包的隔离测试数字代替真实样本条数。

## 七 交回组长的最小清单

- README_member1.md：采集部分步骤可并入全组README。
- data/samples/raw/member1/：运行成功后生成的全部内容，包含实际抽样说明、数据、映射与哈希。
- crawler/export_raw_samples.py、crawler/_member1_common.py：重建样本。
- crawler/audit_source_sizes.py及metadata/source_size_audit.json：动态规模核算。
- metadata/member1_sample_export_receipt.json：本机成功导出回执。
- crawler/download_public_sources.py：来源文档附录独立版，保持“未在本次执行”说明。

其他原始代码、来源文档、全量manifest、日志和映射已在此前交接，不需要重新编造。无需成员1补做清洗、融合表、多源最终关联图、回归或聚类。README并入主仓库和上传GitHub的操作由全组按分工实际执行，本说明不声称已代为上传。
