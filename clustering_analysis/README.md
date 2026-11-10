# 成员 5 出发机场聚类

本模块使用成员 2 的 2024 年 BTS 航班与 NOAA Global Hourly 天气融合主表。主分析纳入 231 个出发机场。Word 报告正文位于 `report/member5_airport_clustering_report.docx`，可并入小组总报告。

## 输入与环境

本模块直接读取 `../data_fusion/data/integrated/flights_weather_2024.parquet`。这份航班与天气融合主表由侯昌杰提供，共有 7,079,060 行、44 列。文件的 SHA-256 校验值如下。

```text
7eb3dc4b1eceaf994207717f3460f6df7d0a519c21b3f4ecb2f9654d592f610b
```

Windows 可在本目录运行 `Get-FileHash ..\data_fusion\data\integrated\flights_weather_2024.parquet -Algorithm SHA256`。以下命令假设已有 Python 3.11 或 3.12 与名为 `.venv` 的虚拟环境。可用 `py -3.11 -m venv .venv` 创建。依赖版本记录在 `requirements.txt`，完整重跑使用 Python 3.12。绘图使用系统中文字体，脚本会优先检测微软雅黑或 Noto Sans CJK SC。

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
.\.venv\Scripts\python.exe .\01_airport_summary.py
.\.venv\Scripts\python.exe .\02_prepare_clustering.py
.\.venv\Scripts\python.exe .\03_evaluate_kmeans.py
.\.venv\Scripts\python.exe .\04_profile_airport_clusters.py
.\.venv\Scripts\python.exe .\05_plot_airport_clusters.py
.\.venv\Scripts\python.exe .\06_check_cluster_sensitivity.py
```

## 输出和核验

| 脚本 | 在 outputs 中生成 |
|---|---|
| `01_airport_summary.py` | `airport_summary.csv`，348 个机场的年度汇总 |
| `02_prepare_clustering.py` | `airport_clustering_input.csv`，筛选后的 231 个机场 |
| `03_evaluate_kmeans.py` | `kmeans_evaluation.csv`，K=2 至 8 的轮廓系数、惯性和组规模 |
| `04_profile_airport_clusters.py` | `airport_cluster_assignments.csv`、`airport_cluster_profiles.csv`，机场归属和分组画像 |
| `05_plot_airport_clusters.py` | `figures/01_cluster_profiles.png`、`figures/02_airport_cluster_scatter.png` |
| `06_check_cluster_sensitivity.py` | `airport_cluster_sensitivity.csv`，强风高值对照及改组机场代码 |

聚类输入为到达延误率、已延误航班的延误分钟中位数、强风比例和低能见度比例。严重延误率用于描述。天气变量各用通过相应质量筛选的匹配有效到达航班计算。机场和分组表中的比例保存为 0 到 1 的小数。组均值按机场等权计算。代表机场是距离该组中心最近的三个机场，距离基于标准化后的四项特征。

复现时检查入选有效到达航班数为 6,893,579，三组机场数依次为 121、30、80，主方案轮廓系数约为 0.2401。两项敏感性检验的 ARI 分别为 0.9797 和 0.9477。成员 5 的 AI 使用记录位于 `AI_USAGE.md`，供合并到小组记录。
