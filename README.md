# 哪些航班更容易延误？——机场、天气与航线特征的关联分析

南京大学「大数据原理与应用」课程小组项目。我们将 2024 年美国 BTS 航班准点数据与 NOAA 逐小时天气观测融合，从时间、机场、天气和航线等角度描述延误特征，并通过回归分析和机场聚类进一步比较不同条件下的延误表现。

## 项目结构与分工

| 模块 | 负责人 | 内容与运行入口 |
| --- | --- | --- |
| 数据采集 | 刘重宏 | 原始数据来源、采集脚本、样本与校验记录。见 [数据采集说明](data_collection/README_member1.md)。 |
| 数据清洗与融合 | 侯昌杰 | 清洗航班和天气数据，处理机场时区并匹配天气，生成一行一班的融合主表。见 [融合说明](data_fusion/README_member2.md)、[字段字典](data_fusion/docs/field_dictionary.md)和[质量报告](data_fusion/docs/quality_report.md)。 |
| 描述性分析 | 朱王祯 | 按时间、机场、航线和天气条件汇总延误，生成统计表和图。见 [描述性分析说明](descriptive_analysis/README_member3.md)。 |
| 回归分析 | 于思源 | 分析延误与天气等特征的关联，并用时间切分评估预测表现。见 [回归运行说明](regression_analysis/README.txt)。报告的 HTML 和 PDF 均在 [回归目录](regression_analysis/)。 |
| 机场聚类 | 游敏凤（组长） | 汇总出发机场特征，比较 K-means 方案，并对三类机场进行画像和敏感性检验。见 [聚类运行说明](clustering_analysis/README.md)。 |

## 与课程建议目录的对应关系

本项目按工作模块组织目录，各类材料与课程建议结构的对应关系如下。

| 课程建议目录 | 本项目对应位置 |
| --- | --- |
| data/raw | data_collection/data/raw 和 data_collection/data/samples/raw |
| data/cleaned | data_fusion/data/cleaned |
| data/integrated | data_fusion/data/integrated |
| crawler | data_collection 中的采集脚本 |
| processing | data_fusion/cleaning |
| analysis | descriptive_analysis、regression_analysis 和 clustering_analysis |
| visualization | 各分析模块中的绘图脚本及 figures 目录 |
| docs | 各模块中的说明文档、质量报告和分析报告 |
| data_sources.md | data_collection/data_sources.md |

复现顺序为：数据采集 → 数据清洗与融合 → 描述性分析 → 回归分析 → 机场聚类。各模块运行入口见上方“项目结构与分工”，具体命令和依赖环境见对应模块说明。回归与聚类均使用完整融合主表，分别按各自说明运行。

## 数据来源与本地存放

- 数据来源包括美国 BTS 航班准点数据、NOAA Global Hourly 天气观测、OurAirports 机场数据及美国 Census 州界数据。数据范围、下载与样本说明见 [数据来源说明](data_collection/data_sources.md)。
- 原始样本位于 [data_collection/data/samples/raw/member1](data_collection/data/samples/raw/member1/)。融合样本位于 [data_fusion/data/integrated](data_fusion/data/integrated/)。样本供查看和检查字段。复现全年统计及模型时使用完整融合主表。
- 完整融合主表共 7,079,060 行、44 列。使用侯昌杰交付的完整融合主表，或按[数据采集说明](data_collection/README_member1.md)和[融合说明](data_fusion/README_member2.md)生成主表，将其放在 `data_fusion/data/integrated/flights_weather_2024.parquet`。聚类脚本默认读取这一位置，回归模块通过运行参数指定主表。主表的 SHA-256 见[聚类运行说明](clustering_analysis/README.md)。

## 查看结果与复现

各分析模块已保存统计表、图和报告，可直接浏览。需要从原始数据复现时，先按采集和融合说明准备主表，再按各分析模块说明配置环境、确认输入路径并运行。回归模块同时使用 Python 和 R。

## AI 使用记录

全组的 AI 使用与人工核验情况见 [AI_USAGE.md](AI_USAGE.md)。
