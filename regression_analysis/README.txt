航班延误回归分析交付说明

数据范围：2024年全年BTS报送航班与匹配NOAA天气。实际读取7,079,060班；未随机抽样。
先打开“航班延误回归分析报告.html”。三张图以base64内嵌，HTML可离线打开或打印，不依赖在线字体与脚本。
tables/保存实际统计结果与核验；figures/保存PNG、PDF、SVG；code/保存可复现脚本。
variable_dictionary.csv说明20个分析字段；AI_USAGE.md记录实际AI参与与仍需人工核验的工作。

数据输入
需要成员2交付的完整 data/integrated/flights_weather_2024.parquet，文件SHA256为：
7eb3dc4b1eceaf994207717f3460f6df7d0a519c21b3f4ecb2f9654d592f610b
本交付不重复打包大型主表或中间CSV；请保留原数据包和其元数据。
预处理脚本核验此SHA256，防止误用其他版本。源文件变更应先核验并显式更新预设校验值。

环境
本次R环境：R version 4.5.3 (2026-03-11 ucrt)；fixest 0.14.2。完整实际环境见R_session_info.txt。
Python依赖在requirements.txt固定到本次使用版本，需Python>=3.11。
R依赖：data.table、fixest、jsonlite。code/install_r_packages.R将这些依赖安装到指定work/r-lib，不修改系统R库。
仅生成HTML使用Python标准库，但自动生成requirements.txt时需要已安装上述Python分析依赖。

推荐的一键执行方式
先进入本交付member4_regression文件夹，确保python与Rscript在PATH中，依次执行：
  python -m pip install -r requirements.txt
  Rscript code/install_r_packages.R work
  .\run_analysis.ps1 -InputParquet "INPUT.parquet"
将INPUT.parquet替换为真实主表的绝对路径。run_analysis.ps1会按顺序运行预处理、模型、评估、报告和最终一致性核验。
在缺少原环境图形QA技能的其他计算机，可加 -SkipFigureQA；此时仍应自行查看最终PNG，不能声称复现了原自动图形核验。

目录与命令
以下命令从项目根目录执行。根目录下放置outputs/member4_regression本交付文件夹，并用work保存中间结果。
请将第一条和第二条命令的 INPUT.parquet 替换为实际主表绝对路径。Windows也可使用带引号的正斜杠路径。

  python outputs/member4_regression/code/prepare_regression.py --input "INPUT.parquet" --work work --out outputs/member4_regression
  python outputs/member4_regression/code/prepare_no_precip.py --input "INPUT.parquet" --work work --out outputs/member4_regression
  Rscript outputs/member4_regression/code/fit_models.R work/model_data.csv outputs/member4_regression work
  Rscript outputs/member4_regression/code/fit_missingness_sensitivity.R work outputs/member4_regression
  python outputs/member4_regression/code/evaluate_and_plot.py --out outputs/member4_regression --work work --bootstrap-repetitions 2000 --block-length 7
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
7日移动块bootstrap共2000次用于Brier/Log loss及其配对差值；未重新拟合模型。
预处理保留y_severe，但本次未另拟合严重延误模型。
本次自动核验不替代原始采集真实性、站点映射、时区转换和教师评分所需的人工核验。
