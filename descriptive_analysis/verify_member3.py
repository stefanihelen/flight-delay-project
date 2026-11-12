from pathlib import Path
import sys,json
from datetime import datetime, timezone, timedelta
import pandas as pd
import pyarrow.parquet as pq
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path('D:/大数据中期大作业')
OUT=Path(__file__).resolve().parent
counts=dict(flights=0,valid_arrivals=0,delayed=0,cancelled=0,diverted=0,matched=0)
monthly={}
for b in pq.ParquetFile(ROOT/'data/integrated/flights_weather_2024.parquet').iter_batches(batch_size=200000,columns=['flight_date','arr_delay_min','arr_del15','cancelled','diverted','weather_match_status']):
 f=b.to_pandas();v=f.cancelled.eq(0)&f.diverted.eq(0)&f.arr_del15.isin([0,1])&f.arr_delay_min.notna()
 counts['flights']+=len(f);counts['valid_arrivals']+=int(v.sum());counts['delayed']+=int((v&f.arr_delay_min.ge(15)).sum());counts['cancelled']+=int(f.cancelled.sum());counts['diverted']+=int(f.diverted.sum());counts['matched']+=int(f.weather_match_status.eq('matched').sum())
 months=pd.to_datetime(f.flight_date).dt.month
 for month in months.unique():
  s=months.eq(month);a=monthly.setdefault(int(month),[0,0,0,0]);a[0]+=int(s.sum());a[1]+=int((s&v).sum());a[2]+=int((s&v&f.arr_delay_min.ge(15)).sum());a[3]+=int(f.loc[s,'cancelled'].sum())
o=pd.read_csv(OUT/'tables/overall.csv').iloc[0]
for k,val in counts.items(): assert int(o[k])==val,(k,val,o[k])
t=pd.read_csv(OUT/'tables/monthly.csv').set_index('month')
for k,vals in monthly.items():
 assert vals==[int(t.loc[k,c]) for c in ['flights','valid_arrivals','delayed','cancelled']]
 assert abs(t.loc[k,'delay_rate']-vals[2]/vals[1])<1e-12
 assert abs(t.loc[k,'cancel_rate']-vals[3]/vals[0])<1e-12
p=OUT/'validation.json';j=json.loads(p.read_text(encoding='utf-8'));j['independent_check']={'status':'passed','checked_at':datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds'),'input_directory':str(ROOT.resolve()),'method':'Parquet分块读取，按延误分钟阈值独立累计总体及每月分子分母','counts':counts};p.write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf-8');print('Independent verification passed:',counts)
