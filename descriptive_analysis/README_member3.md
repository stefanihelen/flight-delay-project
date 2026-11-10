# 成员3交付说明

负责人：朱王祯。范围：描述性统计、时间空间汇总、天气分组和初步相近条件比较。不代做成员4的逻辑回归或成员5的聚类。

## 阅读顺序

1. 第三部分_描述性统计报告.md：正文与七张图。
2. tables：可用Excel打开的UTF-8统计表，所有率为0–1小数；按百分比格式查看。
3. AI_USAGE.md：实际AI参与记录及待人工审核事项。
4. validation.json：实际运行核验与环境版本。

## 复现

依赖：Python 3.11+、pandas、numpy、pyarrow、matplotlib。实际版本见validation.json。

```powershell
python member3_descriptive.py "D:\大数据中期大作业"
python verify_member3.py "D:\大数据中期大作业"
```

参数是成员2交付包根目录。结果写入脚本所在目录的tables、figures和报告文件，重新运行会更新这些结果。读取全年部分列，建议留出数GB可用内存；不需要联网。原始数据不修改。

## 表格说明

flights＝全部计划航班数；valid_arrivals＝未取消、未备降且标签及分钟有效的航班数；delayed＝同口径延误≥15分钟数；delay_rate＝delayed/valid_arrivals；cancel_rate＝cancelled/flights；divert_rate＝diverted/flights。mean/median/p90_delay_min仅基于有效到达。无有效样本的率保留空值，不填0。

monthly、weekday、hourly、month_hour为时间表；airports、states、airlines、routes为机场/空间/航司/有向航线表；numeric_summary保留分位数和缺失；weather_missingness以matched为分母；missingness_all只报告所读原始分析字段的全表缺失。weather_coverage列出匹配状态。

wind_bin和vis_bin左闭右开；precip_bin仅对1小时累计区分有雨无雨，非1小时及缺测独立列出。90min/60min/quality_1_5是三个分析范围，后者在90分钟匹配基础上按对应要素质量码筛选。airport_stratum/route_stratum固定7月、本地12–17时、风速[5,10)节和能见度≥10000米；display_eligible表示有效到达≥200，不表示统计显著。


## 本次修订与局部复现

只重绘热力图，可在成果目录执行：

```powershell
python plot_month_hour.py
python verify_member3.py "D:\大数据中期大作业"
```

plot_month_hour.py读取现有tables/month_hour.csv，仅更新figures/03_month_hour.png；完整分析脚本也调用同一绘图函数。有效到达数n<100的格子灰显并标注n，完整统计仍保留。100是本次修订选定的展示规则，不是老师规定；修改门槛时还须同步报告文字。

本次人工复验之后已在完整输入目录运行verify_member3.py，validation.json中的independent_check.status为passed，含北京时间和实际输入路径。完整重跑member3_descriptive.py会生成新一轮统计并将独立核验重置为pending，因此必须随后运行verify_member3.py；不要仅手工修改状态。图表表达及可复现性来自课程要求，小样本具体门槛和JSON记录形式属于本次完善方案。逐项改动见修改说明.md。
