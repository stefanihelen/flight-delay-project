param(
    [Parameter(Mandatory=$true)][string]$InputParquet,
    [switch]$SkipFigureQA
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $InputParquet).Path
Push-Location -LiteralPath $PSScriptRoot
try {
    New-Item -ItemType Directory -Force -Path 'work' | Out-Null
    python 'code/prepare_regression.py' --input $sourcePath --work 'work' --out '.'
    if ($LASTEXITCODE -ne 0) { throw 'Main preprocessing failed.' }
    python 'code/prepare_no_precip.py' --input $sourcePath --work 'work' --out '.'
    if ($LASTEXITCODE -ne 0) { throw 'Expanded-cohort preprocessing failed.' }
    Rscript 'code/fit_models.R' 'work/model_data.csv' '.' 'work'
    if ($LASTEXITCODE -ne 0) { throw 'Main regression models failed.' }
    Rscript 'code/fit_missingness_sensitivity.R' 'work' '.'
    if ($LASTEXITCODE -ne 0) { throw 'Missingness sensitivity models failed.' }
    $evaluationArgs = @('code/evaluate_and_plot.py','--out','.','--work','work','--bootstrap-repetitions','2000')
    if ($SkipFigureQA) { $evaluationArgs += '--skip-qa' }
    python @evaluationArgs
    if ($LASTEXITCODE -ne 0) { throw 'Prediction evaluation or figure QA failed.' }
    python 'code/build_report.py' --out '.'
    if ($LASTEXITCODE -ne 0) { throw 'Report generation failed.' }
    python 'code/verify_results.py' --out '.'
    if ($LASTEXITCODE -ne 0) { throw 'Final numerical consistency checks failed.' }
} finally {
    Pop-Location
}
