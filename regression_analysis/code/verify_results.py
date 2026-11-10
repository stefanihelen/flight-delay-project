"""Independent numerical consistency checks for the delivered regression results."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1])
a=p.parse_args(); out=a.out.resolve(); tab=out/'tables'
audit=json.loads((tab/'data_audit.json').read_text(encoding='utf-8'))
assert audit['status']=='passed' and audit['expected_sha256_match']
assert audit['input_rows']==7079060 and audit['main_valid_arrivals']==6272073
assert all(v==0 for v in audit['checks'].values())
models=json.loads((tab/'model_diagnostics.json').read_text(encoding='utf-8'))
missing=json.loads((tab/'missingness_models.json').read_text(encoding='utf-8'))
expected={'main','window60','strict_quality','route_fe','disruption','predict_baseline','predict_weather'}
assert set(models)==expected
assert set(missing)=={'no_precip_common','no_precip_expanded'}
for name,m in (models|missing).items():
    assert m['converged'],name
    assert m['n_model']+m['removed_by_estimator']==m['n_eligible'],name
    assert m['cluster_df']==min(m['origins'],m['dates'])-1,name
    assert not m.get('warnings'),(name,m.get('warnings'))
for file in ['weather_contrasts.csv','missingness_contrasts.csv']:
    c=pd.read_csv(tab/file)
    assert np.isfinite(c[['log_or','se','odds_ratio','lower','upper']].to_numpy()).all()
    assert np.allclose(np.exp(c.log_or),c.odds_ratio,rtol=1e-10)
    assert (c.lower<=c.odds_ratio).all() and (c.odds_ratio<=c.upper).all()
    assert (c.se>0).all()
metrics=pd.read_csv(tab/'prediction_metrics.csv')
for r in metrics.itertuples():
    assert r.tp+r.fp+r.fn+r.tn==r.n
    assert np.isclose((r.tp+r.tn)/r.n,r.accuracy)
    assert np.isclose((r.tp+r.fn)/r.n,r.prevalence)
    assert np.isclose(2*r.tp/(2*r.tp+r.fp+r.fn),r.f1)
    assert 0<=r.roc_auc<=1 and 0<=r.average_precision<=1 and 0<=r.brier<=1
for split,g in metrics.groupby('split'):
    assert len(g)==2 and g.n.nunique()==1 and g.prevalence.nunique()==1,split
thresholds=pd.read_csv(tab/'threshold_selection.csv')
for model,g in thresholds.groupby('model'):
    chosen=g[g.selected.astype(str).str.lower()=='true']
    assert len(chosen)==1
    assert np.isclose(chosen.f1.iloc[0],g.f1.max())
    assert np.allclose(metrics.loc[metrics.model==model,'threshold'],chosen.threshold.iloc[0])
for stem in ['01_weather_associations','02_temporal_test_roc','03_temporal_test_calibration']:
    for ext in ['png','pdf','svg']:
        assert (out/'figures'/f'{stem}.{ext}').stat().st_size>1000
assert (out/'航班延误回归分析报告.html').stat().st_size>10000
result={'status':'passed','input_rows':audit['input_rows'],'fitted_models':len(models)+len(missing),
        'main_n':models['main']['n_model'],'model_convergence_and_attrition':'passed',
        'odds_ratio_and_interval_ordering':'passed','prediction_confusion_matrix_and_thresholds':'passed',
        'deliverable_files':'passed','scope':'Numerical/file consistency only; independent of separate visual inspection.'}
(tab/'final_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
