"""Build a self-contained Chinese report from completed, observed results only.

Run after both R model scripts and evaluate_and_plot.py have completed. The
builder fails if required models, figures, or evaluation outputs are missing.
No regression, simulated observations, or result substitution occurs here.
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import importlib.metadata
import json
import platform
import re
from datetime import datetime
from pathlib import Path

NAMES = {
    "wind_5_10": "风速5至不足10节，相对不足5节",
    "wind_10_20": "风速10至不足20节，相对不足5节",
    "wind_20_plus": "风速至少20节，相对不足5节",
    "visibility_5_10km": "能见度5至不足10公里，相对至少10公里",
    "visibility_1_5km": "能见度1至不足5公里，相对至少10公里",
    "visibility_under_1km": "能见度不足1公里，相对至少10公里",
    "rain_vs_dry": "1小时有降水，相对无降水",
    "temperature_5_to_15": "温度由5°C升至15°C",
    "temperature_15_to_25": "温度由15°C升至25°C",
}
MODEL_NAMES = {
    "main": "主模型，90分钟匹配",
    "window60": "匹配窗口缩为60分钟",
    "strict_quality": "四要素质量码均为1或5",
    "route_fe": "航线固定效应替代机场与航程",
    "disruption": "取消、备降或延误的复合结果",
    "predict_baseline": "预测模型，仅控制变量",
    "predict_weather": "预测模型，控制变量与天气",
    "no_precip_common": "无降水项，原完整记录样本",
    "no_precip_expanded": "无降水项，扩展样本",
}
STAGE_NAMES = {
    "all_input": "融合主表全部航班",
    "matched_weather_0_to_90_min": "天气匹配成功且距计划起飞0至90分钟",
    "four_weather_values_finite": "温度、风速、能见度、降水均有有限数值",
    "four_weather_quality_usable": "四要素质量码均在预设接受集合",
    "precipitation_period_one_hour": "降水累计期恰为1小时",
    "nonnegative_wind_visibility_precipitation": "风速、能见度、降水非负",
    "valid_controls_and_distance": "控制字段有效且航程为正",
}
REFS = [
    ("BTS航班字段及到达延误指标定义", "https://www.transtats.bts.gov/DL_SelectFields.aspx?QO_fu146_anzr=b0-gvzr&gnoyr_VQ=FGJ"),
    ("NOAA ISD数据格式与质量码", "https://www.ncei.noaa.gov/pub/data/noaa/isd-format-document.pdf"),
    ("fixest固定效应广义线性模型文档", "https://lrberge.github.io/fixest/reference/feglm.html"),
    ("scikit-learn数据泄漏与预处理说明", "https://scikit-learn.org/stable/common_pitfalls.html"),
    ("scikit-learn预测评估指标文档", "https://scikit-learn.org/stable/modules/model_evaluation.html"),
    ("AI Econ Wiki经验方法工作流", "https://velikov-mihail.github.io/ai-econ-wiki/concepts/empirical-methods/"),
    ("AI Econ Wiki数据分析工作流", "https://velikov-mihail.github.io/ai-econ-wiki/concepts/data-analysis-workflows/"),
]


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def number(value, digits=0) -> str:
    return f"{float(value):,.{digits}f}"


def pct(value, digits=2) -> str:
    return f"{float(value) * 100:.{digits}f}%"


def fmt_or(row) -> str:
    return f"{float(row['odds_ratio']):.3f}（{float(row['lower']):.3f}–{float(row['upper']):.3f}）"


def pformat(value) -> str:
    x = float(value)
    return f"{x:.2e}" if x < 0.001 else f"{x:.3f}"


def table(headers, rows, caption="", classes="") -> str:
    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return (f'<div class="table-wrap"><table class="{classes}">{cap}<thead><tr>'
            + "".join(f"<th>{esc(h)}</th>" for h in headers) + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in row) + "</tr>" for row in rows)
            + "</tbody></table></div>")


def figure(path: Path, caption: str) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f'<figure><img src="data:image/png;base64,{data}" alt="{esc(caption)}"><figcaption>{esc(caption)}</figcaption></figure>'


def csv_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def variable_rows() -> list[dict]:
    entries = [
        ("y_delay", "主要目标", "arr_delay_min, arr_del15, cancelled, diverted", "0/1；无有效到达记-1，仅用于样本标识", "未取消、未备降、到达分钟有限且原标签有效；延误至少15分钟为1，否则0", "主回归和预测仅使用y_delay>=0；提前到达属于0"),
        ("y_severe", "预处理保留目标", "arr_delay_min", "0/1；无有效到达记-1", "有效到达延误至少60分钟为1", "本次未另行拟合严重延误模型；不得将其称为已完成稳健性检验"),
        ("y_disrupt", "敏感性目标", "cancelled, diverted, y_delay", "0/1；无法判断记-1", "取消、备降或到达延误至少15分钟任一成立为1；有效且未延误为0", "分母包含取消和备降，估计对象与主模型不同"),
        ("wind", "核心天气变量", "wind_speed_kts", "节；1节约0.5144米/秒", "0:<5；1:[5,10)；2:[10,20)；3:>=20", "分类哑变量；0为参照，不按整数连续回归"),
        ("vis", "核心天气变量", "vis_m", "原始米；报告转换为公里", "0:>=10000；1:[5000,10000)；2:[1000,5000)；3:<1000", "分类哑变量；0为参照；分组为分析区间而非统一气象标准"),
        ("rain", "核心天气变量", "precip_mm, precip_period_h", "1小时累计毫米", "主样本累计期为1小时；有降水为1，零降水为0", "表示任何有记录降水，不特指液态雨；扩展队列该列是0占位且禁止入模"),
        ("temp10", "核心天气变量", "temp_c", "每10°C", "(temp_c-15)/10", "与平方项联合解释；15°C是预先固定中心"),
        ("temp10sq", "温度非线性", "temp10", "无量纲平方", "temp10的平方", "温度对比通过两项线性组合及完整协方差求区间"),
        ("distance_log", "航程控制", "distance_miles", "英里", "ln(distance_miles/500)，仅保留正航程", "航线固定效应规格删除此项，避免近乎固定的航程被重复控制"),
        ("origin", "机场控制和聚类维度", "origin", "出发机场代码", "吸收固定效应；另用于聚类协方差", "不是整数顺序变量；航线固定效应规格替代此项"),
        ("dest", "机场控制", "dest", "到达机场代码", "吸收固定效应", "控制稳定机场差异，不替代目的地当时天气"),
        ("airline", "航司控制", "reporting_airline", "航司代码", "吸收固定效应", "不将代码大小解释为等级"),
        ("month", "季节控制", "flight_date", "1至12月", "全年关联模型吸收月份固定效应", "预测模型改用预设两组年度Fourier谐波，避免未见月份水平"),
        ("weekday", "星期控制", "flight_date", "1=周一，7=周日", "吸收固定效应", "不是星期每增加1天的线性效应"),
        ("hour", "起飞时段控制", "sched_dep_local", "出发地当地小时0至23", "吸收固定效应", "使用计划起飞小时，不用实际起飞时刻或延误后时刻"),
        ("date_id", "日期和聚类维度", "flight_date", "距2024-01-01天数", "出发地运营日；用于日期聚类、时间划分及Fourier项", "双向聚类为origin与date_id两个维度，不是origin×date_id单维聚类"),
        ("route", "替代固定效应", "origin, dest", "有向航线代码", "origin_dest", "替代出发/到达机场固定效应及航程项，不与它们重复堆叠"),
        ("station", "天气匹配追溯", "station_id", "站点字符串", "保留11位站号", "读取时保持字符；本次未将其另作模型固定效应"),
        ("strict_q", "质量筛选标识", "temp_q, wind_speed_q, vis_q, precip_q", "0/1", "主队列四要素质量码均为1或5时为1", "扩展无降水队列只检查前三要素，不与原队列标识混淆"),
        ("within60", "匹配窗口筛选", "weather_gap_minutes", "0/1", "计划起飞与天气观测间隔不超过60分钟", "主队列已限制0至90分钟；此标识用于缩窄窗口"),
    ]
    return [dict(variable=a, role=b, source_fields=c, unit=d, definition=e, handling_and_limits=f) for a,b,c,d,e,f in entries]


def write_supporting(out: Path, audit: dict, evaluation: dict, session: str) -> None:
    with (out / "variable_dictionary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        rows = variable_rows()
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    packages = ["numpy", "pandas", "pyarrow", "scipy", "matplotlib", "scikit-learn", "PyMuPDF"]
    versions = {name: importlib.metadata.version(name) for name in packages}
    requirements = [f"# Actual Python environment used to build this bundle: {platform.python_version()}",
                    "# Python >=3.11 is required for hashlib.file_digest.",
                    "# R dependencies are listed in README.txt, not pip requirements."]
    requirements += [f"{name}=={version}" for name, version in versions.items()]
    (out / "requirements.txt").write_text("\n".join(requirements)+"\n", encoding="utf-8")
    r_version = next((line for line in session.splitlines() if line.startswith("R version")), "详见R_session_info.txt")
    bootstrap = evaluation["bootstrap"]
    readme = f"""航班延误回归分析交付说明

数据范围：2024年全年BTS报送航班与匹配NOAA天气。实际读取{audit['input_rows']:,}班；未随机抽样。
先打开“航班延误回归分析报告.html”。三张图以base64内嵌，HTML可离线打开或打印，不依赖在线字体与脚本。
tables/保存实际统计结果与核验；figures/保存PNG、PDF、SVG；code/保存可复现脚本。
variable_dictionary.csv说明20个分析字段；AI_USAGE.md记录实际AI参与与仍需人工核验的工作。

数据输入
需要成员2交付的完整 data/integrated/flights_weather_2024.parquet，文件SHA256为：
{audit['input_sha256']}
本交付不重复打包大型主表或中间CSV；请保留原数据包和其元数据。
预处理脚本核验此SHA256，防止误用其他版本。源文件变更应先核验并显式更新预设校验值。

环境
本次R环境：{r_version}；fixest 0.14.2。完整实际环境见R_session_info.txt。
Python依赖在requirements.txt固定到本次使用版本，需Python>=3.11。
R依赖：data.table、fixest、jsonlite。code/install_r_packages.R将这些依赖安装到指定work/r-lib，不修改系统R库。
仅生成HTML使用Python标准库，但自动生成requirements.txt时需要已安装上述Python分析依赖。

推荐的一键执行方式
先进入本交付member4_regression文件夹，确保python与Rscript在PATH中，依次执行：
  python -m pip install -r requirements.txt
  Rscript code/install_r_packages.R work
  .\\run_analysis.ps1 -InputParquet "INPUT.parquet"
将INPUT.parquet替换为真实主表的绝对路径。run_analysis.ps1会按顺序运行预处理、模型、评估、报告和最终一致性核验。
在缺少原环境图形QA技能的其他计算机，可加 -SkipFigureQA；此时仍应自行查看最终PNG，不能声称复现了原自动图形核验。

目录与命令
以下命令从项目根目录执行。根目录下放置outputs/member4_regression本交付文件夹，并用work保存中间结果。
请将第一条和第二条命令的 INPUT.parquet 替换为实际主表绝对路径。Windows也可使用带引号的正斜杠路径。

  python outputs/member4_regression/code/prepare_regression.py --input "INPUT.parquet" --work work --out outputs/member4_regression
  python outputs/member4_regression/code/prepare_no_precip.py --input "INPUT.parquet" --work work --out outputs/member4_regression
  Rscript outputs/member4_regression/code/fit_models.R work/model_data.csv outputs/member4_regression work
  Rscript outputs/member4_regression/code/fit_missingness_sensitivity.R work outputs/member4_regression
  python outputs/member4_regression/code/evaluate_and_plot.py --out outputs/member4_regression --work work --bootstrap-repetitions {bootstrap['repetitions']} --block-length {bootstrap['block_length_days']}
  python outputs/member4_regression/code/build_report.py --out outputs/member4_regression
  python outputs/member4_regression/code/verify_results.py --out outputs/member4_regression

执行顺序
两个预处理脚本流式读取，每批25万行；全部模型使用完整合格队列。
fit_models.R先完成全年关联、敏感性和训练期预测模型，再写出work/holdout_predictions.csv。
fit_missingness_sensitivity.R拟合相同无降水公式在原队列与扩展队列上的模型。
evaluate_and_plot.py读取真实预测，选择验证集阈值，评估共同可预测样本，并生成三张图。
build_report.py必须等所有模型、评估、图均已完成后执行；输入不齐全时会报错，不能用占位结果生成报告。
verify_results.py在报告生成后核对OR、区间、样本数、混淆矩阵、阈值和交付文件，并记录tables/final_verification.json。
代码中所有路径均可通过上述显式参数指定。R的可执行文件不在PATH时，使用本机Rscript.exe完整路径。
任务原环境使用了本地work/r-lib保存R包；其他环境也可安装到标准R库。

图形核验
图形脚本默认调用原环境的nature-figure检查脚本。其他计算机如未安装该技能，可在复现评估时加 --skip-qa，
或用 --qa-scripts 指向同等检查脚本目录；这不表示图形已通过自动核验，交付前仍应人工查看三个PNG。
QA中间图与日志保存在work/figure_qa，不属于需提交的分析结果。

解释边界
OR为优势比，不是概率比；相关性不能写成因果影响。
主结果以有效到达航班为条件；取消/备降另在复合结果中分析。
12月降水缺失明显，必须连同无降水扩展样本敏感性结果解读。
model_data_no_precip.csv中的rain=0是兼容字段占位，禁止进入扩展队列公式；并不表示无雨。
预测窗口是计划起飞前最近天气，不能称为提前一天预测。
AP使用average_precision_score，并非梯形积分PR-AUC。ROC-AUC与AP只有点估计。
{bootstrap['block_length_days']}日移动块bootstrap共{bootstrap['repetitions']}次用于Brier/Log loss及其配对差值；未重新拟合模型。
预处理保留y_severe，但本次未另拟合严重延误模型。
本次自动核验不替代原始采集真实性、站点映射、时区转换和教师评分所需的人工核验。
"""
    (out / "README.txt").write_text(readme, encoding="utf-8")
    ai = """# AI 使用记录与核验说明

日期：2026-11-07。工具：Codex，当前会话及其协作子代理。未将未知具体模型版本写成已知事实。

## 实际参与

用户要求根据课程作业选取回归变量、定义延误目标、处理类别变量、拟合与评估模型，并解释关联方向、不确定性及回归问题。AI读取作业要求、成员3汇总成果和成员2融合主表及元数据；完成变量设计、流式预处理、固定效应Logit代码、时间外推评估、缺失选择敏感性、图表和报告生成。协作子代理分别核对作业要求、回归设计、样本处理与图形评估。

## 代表性指令与采用情况

- “选取合适的回归变量进行分析，使其能契合作业要求”：采用天气＋计划时间、航司、机场与航程控制的二分类Logit；说明这是方法选择，教师并未指定Logit。
- “定义延误目标变量、拟合和评估、解释不确定性”：采用到达延误至少15分钟、双向机场/日期聚类区间，以及按时间切分的独立预测评估。
- “避免时间泄漏并处理类别变量”：全年关联采用月份固定效应；预测改用预设年度Fourier项，避免训练集没有11–12月类别却直接预测的错误。类别作为哑变量或吸收固定效应，不按代码大小回归。

## 核验和修正

已执行的自动核验包括输入SHA256、全量行数、航班ID哈希唯一性、原延误标签与15分钟阈值一致、天气观测与计划起飞时间差、无未来观测、分阶段筛选损失、模型收敛与估计器删样本、预测覆盖和共同评估样本。详见tables内审计文件与模型诊断。哈希唯一性证明的是提供的flight_id无重复，不证明上游航班实体解析完全正确。

发现12月完整天气样本保留率显著下降后，追查到降水缺失并增加无降水扩展队列；在相同公式下比较原队列和扩展队列，避免将删变量与改样本混为一谈。NOAA质量码9不能普遍解释为缺失；主样本使用预设保守接受集合，未接受码不自动等于错误。本主表四要素中未发现数值存在且码为9的记录。

没有将成员3分组表冒充逐航班联合数据；收到主表后实际读取全年而非抽样。没有将OR写为概率比、将AP写为梯形PR-AUC、将区间跨1写成“无关联”，也没有将分组温度结果简化为普遍线性升降温影响。原始源记录、站点映射及完整采集过程未在本次从头重建。

## 人工责任与待完成事项

本记录不声称已经完成学生或教师人工审核。学生应核对数据源许可与规模、关联字段和站点映射、抽查原始记录、理解筛选条件与公式，核对最终表图和结论，并依据真实过程补充自己的学习心得。模型和图表如在随后修改，应重新运行并更新核验记录；不应仅手工修改“passed”状态。

## 反思

AI加快了字段审查、代码实现、全量计算和一致性核验，但不能弥补资料缺失或替代对模型估计对象的判断。完整记录分析仍存在选择偏差；大样本显著性不等于重要性或因果性。对数值警告、概率校准、短测试期和跨年推广的限制需要如实保留。协作审查帮助发现月份类别外推与降水缺失问题，但独立原始记录核查仍需学生完成。
"""
    (out / "AI_USAGE.md").write_text(ai, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    out = args.out.resolve(); tab = out / "tables"
    load = lambda name: json.loads((tab / name).read_text(encoding="utf-8-sig"))
    audit = load("data_audit.json")
    expanded = load("no_precip_data_audit.json")
    diagnostics = load("model_diagnostics.json")
    missing_models = load("missingness_models.json")
    evaluation = load("evaluation.json")
    session = (out / "R_session_info.txt").read_text(encoding="utf-8-sig")
    contrasts = csv_rows(tab / "weather_contrasts.csv")
    missing_contrasts = csv_rows(tab / "missingness_contrasts.csv")
    metrics = csv_rows(tab / "prediction_metrics.csv")
    coverage = csv_rows(tab / "coverage.csv")
    differences = csv_rows(tab / "paired_metric_differences.csv")
    calibration = csv_rows(tab / "calibration.csv")
    dummy = csv_rows(tab / "dummy_baseline_metrics.csv")
    monthly = csv_rows(tab / "no_precip_sample_by_month.csv")
    required_models = {"main", "window60", "strict_quality", "route_fe", "disruption", "predict_baseline", "predict_weather"}
    if not required_models.issubset(diagnostics):
        raise RuntimeError(f"Missing finished models: {sorted(required_models - set(diagnostics))}")
    if not {"no_precip_common", "no_precip_expanded"}.issubset(missing_models):
        raise RuntimeError("Missing completed no-precipitation models")
    if not all(diagnostics[name]["converged"] for name in required_models):
        raise RuntimeError("A required model did not converge")
    if not all(row["converged"] for row in missing_models.values()):
        raise RuntimeError("Missingness sensitivity did not converge")
    for name in ["01_weather_associations", "02_temporal_test_roc", "03_temporal_test_calibration"]:
        if not (out / "figures" / f"{name}.png").exists():
            raise RuntimeError(f"Figure is missing: {name}")
    if audit["status"] != "passed" or expanded["status"] != "passed":
        raise RuntimeError("Input audit did not pass")
    c = {(row["model"], row["contrast"]): row for row in contrasts}
    mc = {(row["model"], row["contrast"]): row for row in missing_contrasts}
    met = {(row["split"], row["model"]): row for row in metrics}
    for contrast in NAMES:
        if ("main", contrast) not in c:
            raise RuntimeError(f"Main contrast missing: {contrast}")
    main_diag = diagnostics["main"]
    main_n = main_diag["n_model"]
    tb, tw = met[("test", "baseline")], met[("test", "weather")]
    test_n = int(tw["n"])
    if int(tb["n"]) != test_n:
        raise RuntimeError("Test models are not evaluated on the same N")
    december = next(row for row in monthly if int(row["month"]) == 12)
    b = evaluation["bootstrap"]
    sections = []
    add = sections.append
    add(f"<h1>航班延误回归分析报告</h1><p class='subtitle'>2024年BTS航班与NOAA天气融合数据｜课程中期项目回归部分｜分析日期2026年11月7日</p>")
    add(f"<p class='lead'>本分析检验天气与到达延误的调整后关联，并比较加入天气信息是否改善未来月份的预测。对全年融合主表的{number(audit['input_rows'])}班航班进行完整读取与核验，主Logit最终使用{number(main_n)}班有效到达航班。强风、低能见度和有降水与更高的延误优势相关；这些结果不构成因果证据。</p>")
    add(f"<div class='callout'>与无降水相比，1小时有降水的调整后优势比为{fmt_or(c[('main','rain_vs_dry')])}；能见度不足1公里相对至少10公里为{fmt_or(c[('main','visibility_under_1km')])}。测试期ROC-AUC从{float(tb['roc_auc']):.3f}变为{float(tw['roc_auc']):.3f}。这些数字的含义、概率校准和样本选择限制须结合下文解读。</div>")
    add("<h2>研究问题与作业要求的对应关系</h2><p>核心问题是：在控制计划起飞时间、航司、机场和航程后，出发机场附近的天气与到达延误是否仍有关联；天气能否提供超出这些航班特征的预测信息。BTS提供航班结果与计划信息，NOAA提供实际天气观测，二者通过机场与气象站匹配以及时间对齐共同进入模型。只有航班数据无法识别天气关联，只有天气数据无法定义航班延误。</p>")
    add(table(["作业要求", "本次对应工作", "边界"], [
        ["至少一种数据挖掘方法", "以Logit完成延误二分类与概率预测", "Logit是本次方法选择，教师没有指定必须使用Logit"],
        ["跨源统一分析与关联解释", "BTS航班与NOAA天气共同进入模型", "只贡献一个跨源核心问题及其子问题"],
        ["质量处理与结果核验", "全量审计、样本流失、模型诊断、预测覆盖和敏感性分析", "不替代原始采集与实体映射核查"],
        ["时空分析及图表", "月份、小时、机场控制与时间外推；3张问题导向图", "全项目5张图、4个独立源、3类来源及3个核心问题仍需全组分别满足"],
        ["可复现和AI披露", "分析代码、结果表、变量字典、README与AI_USAGE", "原始规模至少2GB等工程要求未由本回归包单独验证"],
    ]))
    add("<p>本模型使用实际BTS—NOAA融合主表，不把多个BTS文件算作多个独立来源。州界归属字段没有与机场固定效应重复入模；OurAirports回退数据在该融合交付中未启用，不能因此声称本回归额外验证了第四个独立来源。</p>")
    add("<h2>分析样本和延误目标</h2><p>主目标为<strong>到达延误至少15分钟</strong>：未取消、未备降，且到达延误分钟有限、原始到达延误标签为0或1的航班进入有效到达分母；由分钟阈值重新定义目标并核对标签。提前到达保留为未延误。取消、备降或结果未知不能简单填成未延误。</p>")
    add(table(["筛选步骤", "全部航班", "有效到达", "相对上一步损失有效到达"], [
        [STAGE_NAMES[row["stage"]], number(row["all_flights"]), number(row["valid_arrivals"]), number(row["removed_valid_arrivals_from_previous"])]
        for row in audit["sample_flow"]
    ]))
    add(f"<p>预处理后有{number(audit['main_valid_arrivals'])}班合格有效到达。估计器再删除{number(main_diag['removed_by_estimator'])}条由完全预测固定效应水平引起的观测，最终为{number(main_n)}班；主模型实际覆盖{number(main_diag['origins'])}个出发机场、{number(main_diag['dates'])}个日期。原始队列与估计样本的区别已记录，不能把估计器自动删样本隐藏在总量中。全部合格记录用于估计，没有用随机小样本替代全年。</p>")
    add("<p>敏感性目标为<strong>取消、备降或到达延误至少15分钟</strong>的复合受扰结果。它保留天气与控制条件合格的取消、备降航班，因此回答的是另一种运行受扰问题，不能与条件于有效到达的延误率混为同一分母。预处理另保留了60分钟严重延误标签，但本次没有拟合对应模型。</p>")
    add("<h2>变量选择和类别处理</h2>")
    selected_roles = {"wind", "vis", "rain", "temp10", "temp10sq", "distance_log", "origin", "dest", "airline", "month", "weekday", "hour"}
    add(table(["变量", "用途和单位", "编码与处理"], [[row["variable"], row["role"]+"；"+row["unit"], row["definition"]+"。"+row["handling_and_limits"]] for row in variable_rows() if row["variable"] in selected_roles]))
    add("<p>风速与能见度分组沿用描述统计，保留非线性且便于说明参照。类别代码只是标签：使用哑变量并省略参照组，或者由fixest吸收固定效应；不会把机场代码、月份或天气类别编码作为连续数值。温度采用预先指定的15°C中心和10°C尺度及平方项，不从测试集估计标准化参数。</p>")
    add("<p>气压、露点和风向不进入本次主模型：气压与露点并非回答本次问题的必要首选变量，加入会扩展完整记录筛选并增加解释复杂度；露点与温度还可能高度相关。风向是圆周量，不能把0–360度直接作为线性大小，同时缺少跑道方向，不宜将风向系数解释为侧风关联。这些是本次预设的简约变量选择，不意味着它们没有预测信息。实际起飞延误、实际到达时刻、延误原因及到达延误分钟不得作为预测特征；其中到达分钟仅用于构造目标，以避免结果泄漏。</p>")
    add("<h2>天气质量与时点核验</h2><p>天气必须匹配成功，并在计划起飞前0–90分钟内。核验使用dep_utc−weather_obs_utc与记录的weather_gap_minutes对照；缩窄至60分钟作为敏感性检验。这里使用的是临近计划起飞时可获得的天气观测，不能称为提前一天预报。</p>")
    add(f"<p>主样本要求四种天气数值有限，风速、能见度和降水非负，降水累计期恰为1小时。质量码接受集合为{esc(', '.join(audit['quality_codes_usable']))}，另比较四要素均为1或5的保守子集。其他码属于预设集合之外，不能自动解释为错误或缺失；NOAA码9表示要素存在时通过粗略范围检查。本主表中四要素数值存在且质量码为9的计数分别为{esc(str(audit['numeric_present_quality_code9_all_input']))}。没有把缺失降水改为零降水，也没有将不同累计时长混在一起。</p>")
    add("<p>有限的极端值未因大小而自动缩尾或删除。分组能见度降低了极端高值对线性斜率的影响，但不能证明异常来源已被纠正。已核验的是交付字段内部的一致性；机场与站点空间映射、源数据真实性及原时区转换没有在本次逐条重建。</p>")
    add("<h2>模型设定与不确定性</h2><pre>logit P(延误≥15分钟 = 1 | 有效到达, X)\n = 风速类别 + 能见度类别 + 有降水\n + (温度−15)/10 + [(温度−15)/10]² + ln(航程英里/500)\n + 出发机场FE + 到达机场FE + 航司FE + 月份FE + 星期FE + 计划起飞小时FE</pre>")
    add(f"<p>使用R fixest::feglm的二项Logit和吸收固定效应。主模型经过{number(main_diag['iterations'])}轮迭代收敛。协方差按<strong>出发机场与日期双向聚类</strong>，容许同机场跨日期以及同日期跨机场的相关性；这不是把“机场×日期”组合当一个聚类。主模型区间使用t分布，自由度min({number(main_diag['origins'])}, {number(main_diag['dates'])})−1={number(main_diag['cluster_df'])}。同一天气观测可能服务多班航班，不能将所有航班视作独立气象观测。</p>")
    add("<p>对数优势系数取指数得到OR。OR大于1表示条件延误优势较高；它不是风险比，也不是延误概率增加相同百分比。温度升高10°C的关联取决于起点，通过一次项与平方项的线性组合和完整协方差计算区间。9项天气对比是预设的描述性比较；95%区间均为逐项区间，不保证9项同时以95%覆盖。P值没有做多重比较校正，在数百万样本下很小的P值也不能替代效应量、实际意义及识别条件。这是探索性调整关联，不是因果检验。</p>")
    add("<h2>调整后的天气关联</h2>")
    add(table(["对比", "OR及95%置信区间", "P值"], [[NAMES[name], fmt_or(c[("main", name)]), pformat(c[("main", name)]["p_value"])] for name in NAMES]))
    temp = c[("main", "temperature_15_to_25")]
    temp_statement = "区间跨过1，数据不能排除该特定对比的OR等于1" if float(temp["lower"]) <= 1 <= float(temp["upper"]) else "区间未跨过1，但仍是调整后的关联"
    add(f"<p>风速至少20节相对不足5节，OR为{fmt_or(c[('main','wind_20_plus')])}；能见度不足1公里为{fmt_or(c[('main','visibility_under_1km')])}；有降水为{fmt_or(c[('main','rain_vs_dry')])}。温度从5°C升至15°C的OR为{fmt_or(c[('main','temperature_5_to_15')])}，从15°C升至25°C为{fmt_or(temp)}，后者{temp_statement}。不能据一次项符号写成“温度越高越不延误”。</p>")
    add(figure(out / "figures/01_weather_associations.png", f"图1 控制航班特征后哪些天气与延误有关？2024年全年BTS＋NOAA，主模型n={number(main_n)}班有效到达；点为调整OR，线为机场与日期双向聚类95%区间。横轴为对数尺度，虚线OR=1；结果不表示因果影响。"))
    add("<h2>匹配窗口 质量与模型规格敏感性</h2>")
    sensitivity_names = ["main", "window60", "strict_quality", "route_fe", "disruption"]
    add(table(["模型", "估计N", "强风OR及95%CI", "低能见度OR及95%CI", "有降水OR及95%CI"], [
        [MODEL_NAMES[name], number(diagnostics[name]["n_model"]), fmt_or(c[(name, "wind_20_plus")]), fmt_or(c[(name, "visibility_under_1km")]), fmt_or(c[(name, "rain_vs_dry")])]
        for name in sensitivity_names
    ], classes="small"))
    add("<p>60分钟窗口检查时间匹配松紧；质量码1/5子集检查观测质量口径；航线固定效应规格以有向航线替代出发机场、到达机场和航程，避免嵌套控制造成共线性；复合受扰结果检查取消和备降被排除后估计对象的变化。规格间OR不完全相同并不意外，不能把Logit系数变化直接解释成某类因素贡献的百分比。</p>")
    warnings = []
    for name, diag in {**diagnostics, **missing_models}.items():
        values = diag.get("warnings") or []
        if isinstance(values, str): values = [values]
        warnings += [(MODEL_NAMES.get(name,name), value) for value in values]
    if warnings:
        add("<div class='callout warning'><p><strong>实际数值警告</strong> 以下内容来自运行记录，不能因模型收敛而省略。</p>"+table(["模型", "运行警告"], warnings)+"<p>如警告涉及聚类协方差的非正定修正，相关区间依赖该数值修正；应作为敏感性结果谨慎解释，不能把修正后的区间当作额外独立验证。</p></div>")
    else:
        add("<p>完成的模型诊断未记录R警告；这不等于不存在模型设定或样本选择偏差。</p>")
    add("<h2>降水缺失与季节性样本选择</h2>")
    add(f"<p>12月天气匹配航班中有{number(december['precip_nonfinite_matched_all'])}班降水数值缺失或非有限。完整天气主队列只保留该月原有效到达的{pct(december['original_main_retention'])}，而不要求降水可用的扩展队列保留{pct(december['expanded_main_retention'])}。因此完整记录模型，特别是11–12月评估，代表的是有完整天气记录的子样本，不能自动推广至全部月份航班。删除缺失并不能消除选择偏差。</p>")
    add(table(["月份", "原有效到达", "完整天气有效到达", "完整保留率", "无降水限制有效到达", "扩展保留率"], [[row["month"], number(row["valid_arrivals_input"]), number(row["original_precip_eligible_main"]), pct(row["original_main_retention"]), number(row["expanded_main_arrivals"]), pct(row["expanded_main_retention"])] for row in monthly], classes="small"))
    add(f"<p>扩展预处理得到{number(expanded['expanded_main_arrivals'])}班有效到达。为区分删变量和改样本，先在原完整队列删除降水项，再以<strong>完全相同的无降水公式</strong>拟合扩展队列。两者最终估计样本分别为{number(missing_models['no_precip_common']['n_model'])}和{number(missing_models['no_precip_expanded']['n_model'])}。扩展CSV的rain列只是0占位，不参与任何扩展模型。</p>")
    add(table(["天气对比", "含降水主模型", "无降水项 原队列", "无降水项 扩展队列"], [[NAMES[name], fmt_or(c[("main",name)]), fmt_or(mc[("no_precip_common",name)]), fmt_or(mc[("no_precip_expanded",name)])] for name in NAMES if name != "rain_vs_dry"], classes="small"))
    add("<p>原队列含降水与不含降水的比较反映调整集合改变，原队列与扩展队列的相同无降水公式比较反映可观察的样本组成敏感性。即使方向稳定，也不能证明降水缺失随机；扩展模型本身省略了降水控制，不用于替代主要天气解释，也不能据此声称降水自身的OR得到验证。</p>")
    add("<h2>时间外推的拟合与评估</h2><p>1–8月训练，9–10月验证并选择阈值，11–12月作为独立测试期。模型比较包括仅控制变量与控制变量加天气，均在相同训练和测试口径下进行。没有随机打散全年，没有类别平衡或过采样。分类阈值在验证集0.05–0.60、步长0.01的网格上最大化F1；并列时取较低阈值，测试集不再调阈值。</p>")
    add("<p>为避免训练没有11–12月类别却无法估计其月份固定效应，预测模型采用预先指定的两组年度Fourier谐波sin(2πd/366)、cos(2πd/366)、sin(4πd/366)、cos(4πd/366)，保留机场、航司、星期和小时固定效应。全年关联模型仍使用月份固定效应；两类模型服务不同目的，不能把全年拟合质量冒充时间外推成绩。类别为训练期无法估计的水平时预测可能缺失，以下报告覆盖并只在两个模型共同可预测记录上比较。</p>")
    add(table(["阶段", "模型", "候选航班", "该模型预测缺失", "共同评估N", "共同覆盖率"], [["验证" if row["split"]=="validation" else "测试", "控制" if row["model"]=="baseline" else "控制＋天气", number(row["total_rows"]), number(row["missing_prediction_rows"]), number(row["common_prediction_rows"]), pct(row["common_coverage_rate"])] for row in coverage], classes="small"))
    add(table(["阶段", "模型", "N", "实际延误率", "ROC-AUC", "AP", "Brier", "Log loss"], [["验证" if row["split"]=="validation" else "测试", "控制" if row["model"]=="baseline" else "控制＋天气", number(row["n"]), pct(row["prevalence"]), number(row["roc_auc"],4), number(row["average_precision"],4), number(row["brier"],4), number(row["logloss"],4)] for row in metrics], classes="small"))
    add("<p>ROC-AUC衡量排序区分度；AP为average_precision_score，概括精确率—召回率表现，不是梯形积分PR-AUC。Brier和Log loss越低越好，评价概率误差。准确率受未延误多数类影响，不作为主要成绩；因此同时报告召回率、精确率、F1和概率校准。</p>")
    add(table(["测试模型", "验证选定阈值", "精确率", "召回率", "F1", "准确率", "TN / FP / FN / TP"], [["控制" if row["model"]=="baseline" else "控制＋天气", number(row["threshold"],2), pct(row["precision"]), pct(row["recall"]), number(row["f1"],3), pct(row["accuracy"]), " / ".join(number(row[k]) for k in ["tn","fp","fn","tp"])] for row in metrics if row["split"]=="test"], classes="small"))
    add(f"<p>天气模型测试ROC-AUC为{float(tw['roc_auc']):.3f}，区分度仍然有限。在验证集选定的阈值{float(tw['threshold']):.2f}下，精确率为{pct(tw['precision'])}，即被判为延误的航班中约{pct(1-float(tw['precision']))}实际未延误；召回率为{pct(tw['recall'])}。按F1选择阈值的准确率为{pct(tw['accuracy'])}，低于把所有航班都判为未延误的{pct(1-float(tw['prevalence']))}，并不矛盾：后者利用多数类而召回率为0，优化目标不同。这些结果不足以称为可靠的运营预警系统，不能在看到测试结果后再调整阈值。</p>")
    add(table(["测试模型", "Brier及95%区间", "Log loss及95%区间"], [["控制" if row["model"]=="baseline" else "控制＋天气", f"{float(row['brier']):.5f}（{float(row['brier_lower']):.5f}–{float(row['brier_upper']):.5f}）", f"{float(row['logloss']):.5f}（{float(row['logloss_lower']):.5f}–{float(row['logloss_upper']):.5f}）"] for row in metrics if row["split"]=="test"]))
    dummy_test = next(row for row in dummy if row["split"]=="test")
    add(f"<p>另以训练期延误率为所有测试航班给出同一概率，常数基线测试Brier为{float(dummy_test['brier']):.4f}，Log loss为{float(dummy_test['logloss']):.4f}。该概率来自训练期，未借用测试期发生率。</p>")
    add(table(["天气减控制的测试损失差", "估计差值", "95%区间", "判断"], [[row["metric"], number(row["estimate"],5), f"{float(row['lower']):.5f} 至 {float(row['upper']):.5f}", "区间完全小于0：天气模型损失较低" if float(row["upper"])<0 else ("区间完全大于0：天气模型损失较高" if float(row["lower"])>0 else "区间跨0：差值不确定")] for row in differences]))
    add(f"<p>损失差与单模型Brier、Log loss区间使用{number(b['repetitions'])}次非循环{number(b['block_length_days'])}日移动块bootstrap，在相同日期块上配对重抽样，保留每日航班数和损失总和。测试期有{number(b['test_calendar_days'])}个日历日，独立时间信息有限。该区间条件于已训练模型和已选阈值，没有重新训练，也不包含训练、调参或未来年份的不确定性。ROC-AUC和AP仅报告点估计，不声称已经计算它们的区间。</p>")
    add(figure(out / "figures/02_temporal_test_roc.png", f"图2 加入天气后能否更好区分未来月份的延误？BTS＋NOAA，2024年11–12月两个模型共同可预测的{number(test_n)}班有效到达；训练1–8月、验证9–10月。ROC使用全部测试分数，图中AUC为点估计。"))
    cal_text = []
    for model in ["baseline", "weather"]:
        rows = [row for row in calibration if row["model"]==model]
        total = sum(float(row["n"]) for row in rows)
        predicted = sum(float(row["n"])*float(row["mean_prediction"]) for row in rows)/total
        observed = float(met[("test",model)]["prevalence"])
        direction = "高于" if predicted > observed else "低于"
        cal_text.append(f"{'控制' if model=='baseline' else '控制＋天气'}模型平均预测{pct(predicted)}，{direction}实际延误率{pct(observed)}，差值{(predicted-observed)*100:+.2f}个百分点")
    add("<h2>概率校准与结果的实际含义</h2><p>"+"；".join(cal_text)+"。排序能力改善不等于概率已准确。校准图按各模型测试概率的分位数最多分10组，展示平均预测和实际发生比例；这些是描述点，没有区间，也没有在测试集上再校准。总体均值相近也不能保证所有概率段都可靠。</p>")
    top_weather = max((row for row in calibration if row["model"]=="weather"), key=lambda row:float(row["mean_prediction"]))
    add(f"<p>例如天气模型最高预测概率组的平均预测为{pct(top_weather['mean_prediction'])}，实际延误比例为{pct(top_weather['observed_rate'])}，说明高风险端的概率仍有偏差。是否需要再校准应在额外开发数据上决定，并用新的独立测试期验证，不能用本测试集拟合后又在同一批航班报告改进。</p>")
    add(figure(out / "figures/03_temporal_test_calibration.png", f"图3 预测的延误概率与实际发生比例是否一致？BTS＋NOAA，2024年11–12月共同可预测样本n={number(test_n)}；横轴为组内平均预测概率，纵轴为实际延误比例。分组点不含置信区间，虚线表示理想一致，不表示模型已通过校准。"))
    add("<h2>已执行核验和仍需处理的问题</h2>")
    checks = audit["checks"]
    check_labels = {
        "flight_id_missing": "航班ID缺失", "duplicate_flight_id_hash_rows": "重复航班ID哈希",
        "flight_date_missing_or_not_2024": "日期缺失或不属于2024年",
        "valid_arrival_label_inconsistency": "到达标签与15分钟阈值不一致",
        "matched_invalid_gap": "匹配记录间隔不在0–90分钟",
        "matched_timestamp_missing": "匹配记录缺少时点",
        "matched_future_weather": "天气观测晚于计划起飞",
        "matched_gap_timestamp_disagreement_gt_0_001min": "时间差与记录相差超过0.001分钟",
        "within60_flag_disagreement": "60分钟标识不一致",
    }
    add(table(["自动核验", "异常计数"], [[label, number(checks[key])] for key,label in check_labels.items()]))
    add(f"<p>源文件SHA256为<code class='hash'>{esc(audit['input_sha256'])}</code>，与交付清单一致。航班ID以分批确定性64位哈希后全局去重核验，无缺失且无重复哈希；相同ID必然产生相同哈希，因此未发现相同ID。这不证明原始记录的实体定义、去重键选择或上游融合过程完全正确。自动核验和协作审查已执行，学生人工审阅未在本记录中冒称完成。</p>")
    add("<ul><li><strong>样本选择：</strong>主模型条件于有效到达和完整天气记录；取消/备降复合结果及扩展样本只是敏感性检查，不能消除未观测选择。</li><li><strong>遗漏和共同决定：</strong>目的地当时天气、空域拥堵、飞机轮转、维修和调度信息未充分控制。机场固定效应不能替代这些随时间变化的条件，因此不主张天气的净因果效应。</li><li><strong>相关观测：</strong>估计按航班计权，同一观测对应多个航班；聚类协方差缓解部分依赖，但不会消除空间相关、跨日天气过程或模型错误。</li><li><strong>非线性和稀有类别：</strong>天气分组及温度二次项只是预设函数形式；完全预测类别自动删除、稀有水平和协方差警告均须报告，不能只展示收敛标志。</li><li><strong>时点和外推：</strong>使用计划起飞前近期观测而不是日提前天气预报；只有一年数据和两个月测试期，不能据此宣称跨年、极端天气或新机场预测已验证。</li><li><strong>解释单位：</strong>优势比、概率比和百分点不是同一量。没有计算平均边际概率效应时不填造百分点结果；温度需联合解释两项。</li><li><strong>大规模工程：</strong>流式每批25万行预处理，固定效应吸收避免手工构造巨大稠密哑变量矩阵。按日志说明内存与耗时，不能把抽样调试结果当作全量最终结果。</li></ul>")
    add("<h2>可复现材料与方法来源</h2><p>README.txt给出从主表到两套队列、R估计、预测评估和本报告的一致执行顺序；变量字典列出全部编码，tables保存系数、协方差、对比、样本流失、覆盖和评估。HTML中的所有模型数字均来自实际结果文件，三张图以base64内嵌。AI参与、修正和未完成的人工责任另见AI_USAGE.md。</p>")
    add("<p><strong>Wiki Check：</strong>方法规划查阅AI Econ Wiki的经验方法和分析工作流缓存（2026年11月3日获取），用于明确估计对象、检查预处理及可复现性。Wiki是工作流参考，不作为回归技术的唯一权威；变量质量码、模型实现和评估定义以下列官方文档为准。</p>")
    add("<ol>"+"".join(f'<li><a href="{esc(url)}">{esc(title)}</a></li>' for title,url in REFS)+"</ol>")
    add("<p class='footer'>范围：2024年BTS报送航班与匹配NOAA天气。报告中的关联、预测和质量核验均有各自的样本范围；原始采集、全项目来源数量和人工审核不能由本回归部分代替。</p>")
    css = """*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#18232e;font-family:'Microsoft YaHei','PingFang SC',Arial,sans-serif;font-size:15px;line-height:1.75}main{max-width:1080px;margin:30px auto;padding:38px 46px 48px;background:#fff}h1{font-size:29px;line-height:1.3;margin:0 0 12px;color:#102d43}h2{font-size:21px;line-height:1.45;margin:34px 0 12px;color:#163b56}p{margin:12px 0}.subtitle,.footer{color:#5a6976;font-size:13px}.lead{font-size:17px}.callout{background:#edf4f8;border-left:4px solid #246e9f;padding:14px 18px;margin:20px 0}.warning{background:#faf4e9;border-color:#a07532}.table-wrap{overflow-x:auto;margin:15px 0}table{border-collapse:collapse;width:100%;font-size:13px;line-height:1.55;text-align:left}th{background:#edf2f6;color:#213e52;font-weight:600}td,th{padding:9px 10px;border-bottom:1px solid #dce3e8;vertical-align:top}tbody tr:nth-child(even){background:#fafbfd}table.small{font-size:12px}caption{text-align:left;font-weight:600;margin-bottom:8px}figure{margin:25px auto;max-width:880px}figure img{display:block;width:100%;height:auto}figcaption{font-size:12px;color:#4c5c69;margin:10px 0 0;line-height:1.6}pre{white-space:pre-wrap;background:#f2f5f7;border:1px solid #dbe3e8;padding:16px;font:14px/1.7 Consolas,'Microsoft YaHei',monospace}code.hash{overflow-wrap:anywhere;font-size:12px}a{color:#1e6187}li{margin:8px 0}strong{font-weight:600}@media(max-width:700px){main{margin:0;padding:24px 18px}h1{font-size:25px}body{font-size:14px}td,th{padding:7px}figure{margin:20px -4px}}@media print{@page{size:A4;margin:16mm}body{background:#fff;font-size:10pt;line-height:1.6}main{max-width:none;margin:0;padding:0}h1{font-size:21pt}h2{font-size:15pt;break-after:avoid}p,li{orphans:3;widows:3}figure{break-inside:avoid;max-width:155mm}table{font-size:8.4pt}table.small{font-size:7.5pt}tr{break-inside:avoid}thead{display:table-header-group}.table-wrap{overflow:visible}a{color:inherit;text-decoration:none}.callout{break-inside:avoid}pre{font-size:9pt}.subtitle,.footer,figcaption{font-size:8pt}}
"""
    document = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>航班延误回归分析报告</title><style>'+css+'</style></head><body><main>'+"\n".join(sections)+'</main></body></html>'
    report_path = out / "航班延误回归分析报告.html"
    report_path.write_text(document, encoding="utf-8")
    write_supporting(out, audit, evaluation, session)
    manifest = {
        "built_at": datetime.now().astimezone().isoformat(), "report": report_path.name,
        "embedded_figures": 3, "main_n": main_n, "test_common_n": test_n,
        "source_results": ["data_audit.json", "no_precip_data_audit.json", "model_diagnostics.json", "missingness_models.json", "weather_contrasts.csv", "missingness_contrasts.csv", "prediction_metrics.csv", "coverage.csv", "paired_metric_differences.csv", "calibration.csv", "dummy_baseline_metrics.csv", "no_precip_sample_by_month.csv", "evaluation.json"],
        "real_results_only": True, "human_review_claimed": False,
    }
    (tab / "report_build.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
