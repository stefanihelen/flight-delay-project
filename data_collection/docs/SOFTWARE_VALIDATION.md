# 补充脚本的软件验证

验证环境：Python 3.12.14（助手隔离环境）；目标运行环境为采集者Python 3.11.9。本包使用与3.11兼容的标准库语法；尚未在采集者真实数据目录运行。

已验证全部Python文件语法，并使用临时隔离夹具完成端到端检查：

- PASS dynamic manifest sizes, no fixed BTS byte constant
- PASS exact original field values, quoted commas, trailing empty header and 2400 kept
- PASS conservative UTC windows: start included, end excluded, preceding day kept
- PASS output hashes, CSV reread, complete auxiliary copy, source files unchanged
- PASS repeated execution refuses to overwrite existing samples
- PASS inconsistent BTS summary is rejected
- PASS missing METAR support rejects export and removes only its temporary output

上述为软件测试，通过不等于真实样本已导出，也不等于全量采集重新核验。夹具仅用于程序测试，未包含在本补充包，不作为课程样本、数据规模、采集日志或统计结论。

真实样本需运行RUN_MEMBER1_SUPPLEMENT.bat后，以自动生成的sample_manifest.json、README.md及导出回执记录的条数、来源与哈希验收。

公网复采示例download_public_sources.py仅做语法检查，没有发起新采集，不宣称已实测公网下载。
