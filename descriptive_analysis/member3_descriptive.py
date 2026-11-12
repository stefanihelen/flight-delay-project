from pathlib import Path
import hashlib,json,sys,platform
import numpy as np
import pandas as pd
import pyarrow
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(sys.argv[1]) if len(sys.argv)>1 else Path('D:/大数据中期大作业')
OUT=Path(__file__).resolve().parent
for n in ['tables','figures']: (OUT/n).mkdir(exist_ok=True)
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False})
src=ROOT/'data/integrated/flights_weather_2024.parquet'
with src.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
assert any(l.split()[0]==sha and l.split()[-1]=='data/integrated/flights_weather_2024.parquet' for l in (ROOT/'metadata/member2_deliverable_checksums.sha256').read_text().splitlines())
cols=['flight_date','sched_dep_local','origin','dest','reporting_airline','origin_polygon_state','arr_delay_min','arr_del15','cancelled','diverted','distance_miles','weather_match_status','weather_match_within_60','weather_gap_minutes','temp_c','wind_speed_kts','vis_m','precip_mm','precip_period_h','wind_speed_q','vis_q','precip_q']
print('Reading full data',flush=True)
d=pd.read_parquet(src,columns=cols)
d['flight_date']=pd.to_datetime(d.flight_date)
d['month']=d.flight_date.dt.month.astype('int8');d['weekday']=(d.flight_date.dt.dayofweek+1).astype('int8');d['hour']=d.sched_dep_local.dt.hour.astype('int8')
v=d.cancelled.eq(0)&d.diverted.eq(0)&d.arr_del15.isin([0,1])&d.arr_delay_min.notna()
m=d.weather_match_status.eq('matched')
d['valid']=v.astype('int8');d['delayed']=(v&d.arr_del15.eq(1)).astype('int8');d['delay_valid']=d.arr_delay_min.where(v)
assert len(d)==7079060 and d.flight_date.dt.year.eq(2024).all()
assert d.loc[v,'arr_del15'].eq(d.loc[v,'arr_delay_min'].ge(15)).all()
assert d.loc[m,'weather_gap_minutes'].between(0,90).all()
assert (~d.weather_match_within_60 | (m&d.weather_gap_minutes.le(60))).all()
def save(t,n):
 t.to_csv(OUT/'tables'/f'{n}.csv',index=False,encoding='utf-8-sig');return t
def agg(f,k):
 t=f.groupby(k,observed=True,dropna=False).agg(flights=('valid','size'),valid_arrivals=('valid','sum'),delayed=('delayed','sum'),cancelled=('cancelled','sum'),diverted=('diverted','sum'),mean_delay_min=('delay_valid','mean'),median_delay_min=('delay_valid','median'),p90_delay_min=('delay_valid',lambda s:s.quantile(.9))).reset_index()
 t['delay_rate']=t.delayed/t.valid_arrivals.replace(0,np.nan);t['cancel_rate']=t.cancelled/t.flights;t['divert_rate']=t.diverted/t.flights
 return t
T={}
for name,keys in [('monthly',['month']),('weekday',['weekday']),('hourly',['hour']),('month_hour',['month','hour']),('airports',['origin']),('states',['origin_polygon_state']),('airlines',['reporting_airline']),('routes',['origin','dest'])]:
 print(name,flush=True);T[name]=save(agg(d,keys),name)
 assert T[name].flights.sum()==len(d) and T[name].valid_arrivals.sum()==v.sum() and T[name].delayed.sum()==d.delayed.sum()
x=d.loc[v,'arr_delay_min']
overall=dict(flights=len(d),valid_arrivals=int(v.sum()),delayed=int(d.delayed.sum()),cancelled=int(d.cancelled.sum()),diverted=int(d.diverted.sum()),delay_rate=float(d.delayed.sum()/v.sum()),cancel_rate=float(d.cancelled.mean()),matched=int(m.sum()),origins=d.origin.nunique(),airlines=d.reporting_airline.nunique(),sha256=sha)
save(pd.DataFrame([overall]),'overall')
stats=[]
for c in ['delay_valid','distance_miles','temp_c','wind_speed_kts','vis_m','precip_mm']:
 s=d[c] if c in ['delay_valid','distance_miles'] else d.loc[m,c]
 row=s.describe(percentiles=[.01,.25,.5,.75,.9,.95,.99]).to_dict();row.update(variable=c,scope_n=len(s),missing=int(s.isna().sum()));stats.append(row)
save(pd.DataFrame(stats),'numeric_summary')
save(pd.DataFrame({'field':cols,'missing':d[cols].isna().sum().values,'missing_rate':d[cols].isna().mean().values}),'missingness_all')
save(d.weather_match_status.value_counts(dropna=False).rename_axis('status').reset_index(name='flights'),'weather_coverage')
wcols=['temp_c','wind_speed_kts','vis_m','precip_mm']
save(pd.DataFrame({'field':wcols,'matched_flights':int(m.sum()),'missing':d.loc[m,wcols].isna().sum().values,'missing_rate':d.loc[m,wcols].isna().mean().values}),'weather_missingness')
d['wind_bin']=pd.cut(d.wind_speed_kts,[-np.inf,5,10,20,np.inf],labels=['<5','5–<10','10–<20','≥20'],right=False).astype(object).fillna('缺测')
d['vis_bin']=pd.cut(d.vis_m,[-np.inf,1000,5000,10000,np.inf],labels=['<1000','1000–<5000','5000–<10000','≥10000'],right=False).astype(object).fillna('缺测')
d['precip_bin']=np.select([d.precip_mm.isna(),~d.precip_period_h.eq(1),d.precip_mm.eq(0)],['缺测','非1小时累计','1小时无降水'],default='1小时有降水')
W={}
for key,q in [('wind_bin','wind_speed_q'),('vis_bin','vis_q'),('precip_bin','precip_q')]:
 for window,mask in [('90min',m),('60min',m&d.weather_match_within_60),('quality_1_5',m&d[q].isin(['1','5']))]:
  n=key+'_'+window;W[n]=save(agg(d.loc[mask],[key]),n)
  assert W[n].flights.sum()==mask.sum() and W[n].valid_arrivals.sum()==(mask&v).sum()
stratum=m&d.month.eq(7)&d.hour.between(12,17)&d.wind_speed_kts.ge(5)&d.wind_speed_kts.lt(10)&d.vis_m.ge(10000)
for keys,name in [(['origin'],'airport_stratum'),(['origin','dest'],'route_stratum')]:
 t=agg(d.loc[stratum],keys);t['display_eligible']=t.valid_arrivals.ge(200);T[name]=save(t,name)
def finish(name,note):
 f=plt.gcf();f.text(.02,.015,note,fontsize=8,color='#444444');f.tight_layout(rect=[0,.09,1,1]);f.savefig(OUT/'figures'/f'{name}.png',dpi=170);plt.close(f)
source='范围：2024年BTS报送航班；来源：BTS；延误率分母：未取消、未备降且标签及分钟数有效的航班。'
plt.figure(figsize=(11,5));labels=['提前到达','0–<15','15–<30','30–<60','60–<120','≥120']
dist=pd.cut(x,[-np.inf,0,15,30,60,120,np.inf],labels=labels,right=False).value_counts(sort=False)
save(dist.rename_axis('delay_minutes_bin').reset_index(name='flights'),'delay_distribution')
plt.bar(labels,dist.values/len(x)*100,color='#236a89');plt.ylabel('有效到达航班占比（%）');plt.xlabel('到达延误分钟分组');plt.title('航班延误分布是否存在长尾？')
finish('01_distribution',source+f'\nn={len(x):,}；保留全部尾部。')
f,axes=plt.subplots(1,2,figsize=(12,5));t=T['monthly']
for ax,col,title in zip(axes,['delay_rate','cancel_rate'],['哪些月份到达延误率更高？','哪些月份取消率更高？']):
 ax.plot(t.month,t[col]*100,marker='o',color='#236a89');ax.set_title(title);ax.set_xticks(range(1,13));ax.set_xlabel('月份');ax.set_ylabel('比率（%）');ax.set_ylim(bottom=0)
finish('02_monthly',source+'\n取消率分母：当月全部计划航班；各月样本量见monthly.csv。')
from plot_month_hour import plot_month_hour
plot_month_hour(T['month_hour'], OUT/'figures/03_month_hour.png')
f,axes=plt.subplots(1,2,figsize=(13,5.5))
for ax,key,title,unit,order in [(axes[0],'wind_bin','风速不同，延误率如何变化？','节',['<5','5–<10','10–<20','≥20','缺测']),(axes[1],'vis_bin','能见度不同，延误率如何变化？','米',['<1000','1000–<5000','5000–<10000','≥10000','缺测'])]:
 t=W[key+'_90min'].set_index(key).reindex(order);ax.bar(range(len(t)),t.delay_rate*100,color='#236a89');ax.set_xticks(range(len(t)),[str(i)+'\nn='+format(int(n),',') for i,n in zip(t.index,t.valid_arrivals)],fontsize=8);ax.set_xlabel(unit);ax.set_ylabel('到达延误率（%）');ax.set_title(title)
finish('04_weather','范围：2024年、起飞前90分钟内匹配成功航班；来源：BTS＋NOAA；n为各组有效到达数。\n分组为描述性区间，非气象标准；缺测不填零。')
plt.figure(figsize=(11,6));t=T['airports'].nlargest(15,'flights').sort_values('delay_rate');plt.barh(t.origin.astype(str),t.delay_rate*100,color='#236a89');plt.xlabel('到达延误率（%）');plt.title('出发航班量最大的15个机场，延误率有何差异？')
finish('05_airports',source+'\n先按全部航班量选15机场，再按延误率排序；样本量见airports.csv；未经天气与航线结构调整。')
plt.figure(figsize=(11,6));t=T['states'].loc[lambda a:a.valid_arrivals.ge(10000)].nlargest(15,'delay_rate').sort_values('delay_rate');plt.barh(t.origin_polygon_state.astype(str),t.delay_rate*100,color='#236a89');plt.xlabel('到达延误率（%）');plt.title('有效到达不少于1万班的州及地区中，哪些延误率较高？')
finish('06_states','范围：2024年；来源：BTS＋成员2已核验的Census州界归属；分母为有效到达航班数。\n按航班数加权，非机场率的简单平均；完整地区及分母见states.csv。')
plt.figure(figsize=(11,6));t=T['airport_stratum'].loc[lambda a:a.display_eligible].nlargest(10,'flights').sort_values('delay_rate');plt.barh(t.origin.astype(str),t.delay_rate*100,color='#236a89');plt.xlabel('到达延误率（%）');plt.title('相同月份、时段及天气分组下，机场表现是否仍有差异？')
finish('07_stratified','来源：BTS＋NOAA；2024年7月本地12–17时，风速[5,10)节，能见度≥10000米，90分钟匹配。\n每机场有效到达≥200，按航班量取前10；仅分层描述；分母见airport_stratum.csv。')
month=T['monthly'];hi=month.loc[month.delay_rate.idxmax()];lo=month.loc[month.delay_rate.idxmin()];wind=W['wind_bin_90min'].set_index('wind_bin');vis=W['vis_bin_90min'].set_index('vis_bin')
lines=['# 第三部分 描述性统计与时空分析','负责人：朱王祯｜计算日期：2026-11-04｜数据期：2024全年',
'## 1 数据与统计口径',f'读取成员2全年融合主表，共{len(d):,}班，覆盖{d.origin.nunique()}个出发机场、{d.reporting_airline.nunique()}个报送航司代码。输入SHA-256：`{sha}`，与交付清单一致。未使用前2万行样本代替全年。研究对象仅为BTS报送范围。',
'延误率＝未取消、未备降且标签和延误分钟有效的延误≥15分钟航班数÷同口径有效到达航班数。取消率和备降率分别以全部计划航班为分母。月份与星期基于flight_date，小时基于sched_dep_local，星期1表示周一。州级使用origin_polygon_state按航班加权，领地保留独立归属。ArrDelay可为负数，表示提前到达。',
'总体与时间空间统计使用全部航班；天气比较仅使用matched（起飞前0–90分钟）记录，缺测独立分组，不填无雨或零风速。降水仅比较1小时累计，其他时长独立列出。同一天气观测可对应多班航班，结果为航班加权而非独立气象观测统计。',
'## 2 总体规模与延误分布',f'有效到达{int(v.sum()):,}班（{v.mean():.2%}），排除{int((~v).sum()):,}班；延误{int(d.delayed.sum()):,}班，延误率**{overall["delay_rate"]:.2%}**。取消{overall["cancelled"]:,}班，取消率**{overall["cancel_rate"]:.2%}**；备降{overall["diverted"]:,}班（{d.diverted.mean():.2%}）。',f'有效到达平均延误{x.mean():.2f}分钟，中位数{x.median():.0f}分钟，P90={x.quantile(.9):.0f}、P95={x.quantile(.95):.0f}、P99={x.quantile(.99):.0f}分钟，最小{x.min():.0f}、最大{x.max():.0f}分钟。均值与中位数差异提示长尾影响。极端值保留，未逐班核实原因，不能直接认定为错误。','![延误分布](figures/01_distribution.png)',
'## 3 时间变化',f'月度延误率最高为{int(hi.month)}月（{hi.delay_rate:.2%}），最低为{int(lo.month)}月（{lo.delay_rate:.2%}）。这是一年月际差异，不能推广为多年稳定规律。月份、星期、本地小时及月份×小时的全部分子分母分别见monthly、weekday、hourly、month_hour表。','![月度趋势](figures/02_monthly.png)','热力图以有效到达数n<100为灰显门槛，并标注n；灰色不代表零延误。100是本次选定的展示规则，非老师规定或显著性标准，n≥100也不保证规律稳定。288格中21格灰显，包括9月4时n=4和10月4时n=6；完整比率与分母仍保留于month_hour.csv。','![月份时段](figures/03_month_hour.png)',
'## 4 天气与运行表现的描述性关联',f'90分钟匹配成功{int(m.sum()):,}班（{m.mean():.2%}）；60分钟内{int(d.weather_match_within_60.sum()):,}班。天气要素缺失见weather_missingness.csv；匹配成功不等于要素全部有效。',f'风速<5节组延误率{wind.loc["<5","delay_rate"]:.2%}，≥20节组{wind.loc["≥20","delay_rate"]:.2%}；能见度<1000米组{vis.loc["<1000","delay_rate"]:.2%}，≥10000米组{vis.loc["≥10000","delay_rate"]:.2%}。这只说明样本内关联，机场、季节、航司、航线结构可能混杂，不能解释为因果。','![天气分组](figures/04_weather.png)',
'天气表同时保留全部航班量、有效到达、延误数、取消数及各自比率。60min表提供窗口敏感性检查；quality_1_5表仅保留该要素质量码1/5，是保守子集检查，不声称其他质量码均错误。不对相关观测套用独立二项假设，不提供未经处理的显著性结论。',
'## 5 机场地区与相近条件比较','机场图先选全年出发量前15再排序；地区图设置有效到达≥1万班门槛，完整机场、州、航司及有向航线表均保留。州归属沿用成员2核验结果；现有包缺少州界几何文件，因此使用州级条形图，未绘制州界地图。','![机场差异](figures/05_airports.png)','![州差异](figures/06_states.png)',f'固定7月、本地12–17时、风速[5,10)节、能见度≥10000米与90分钟匹配，共{int(stratum.sum()):,}班，有效到达{int((stratum&v).sum()):,}班。机场和有向航线分层表采用有效到达≥200的展示门槛。该预设分层只示范相近条件比较，仍有组内天气及航线、航司差异，不能称为回归调整后的排名。','![分层比较](figures/07_stratified.png)',
'## 6 交接与局限','天气分组提供第一个核心问题的描述性证据；机场与航线分层提供第二个问题的初步证据；时空汇总为区域季节问题提供基础。单独的BTS月度或州级统计不能冒充完整多源核心问题答案。成员4继续回归调整，成员5在机场表基础上另定覆盖门槛及特征标准化。',
'本次实际自动核验包括输入校验值、全年行数、年份、标签阈值一致性、天气时间窗口、各分组行数/有效分母/延误数加总。未重新执行原始采集、全量清洗或逐条人工核查，原始规模≥2GB、单源占比和三类来源要求仍须全组用采集材料验证。AI实际协助与待人工审核事项见AI_USAGE.md。']
(OUT/'第三部分_描述性统计报告.md').write_text('\n\n'.join(lines),encoding='utf-8')
validation=dict(input_sha256_match=True,rows=len(d),valid_arrivals=int(v.sum()),label_consistency=True,group_totals_reconcile=True,weather_windows_valid=True,python=platform.python_version(),pandas=pd.__version__,pyarrow=pyarrow.__version__,matplotlib=matplotlib.__version__,independent_check='pending')
(OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(overall,ensure_ascii=False,indent=2),flush=True)
