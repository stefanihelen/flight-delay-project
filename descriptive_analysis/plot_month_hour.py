"""仅重绘月份×本地小时热力图，不重新计算统计表。"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

MIN_VALID_ARRIVALS = 100  # 本次展示规则，非课程指定门槛或显著性标准。

def plot_month_hour(table, output):
    rates = table.pivot(index='month', columns='hour', values='delay_rate').reindex(index=range(1,13), columns=range(24))
    counts = table.pivot(index='month', columns='hour', values='valid_arrivals').reindex(index=range(1,13), columns=range(24))
    mask = counts.lt(MIN_VALID_ARRIVALS) | counts.isna() | rates.isna()
    data = np.ma.array(rates.to_numpy()*100, mask=mask.to_numpy())
    cmap = plt.get_cmap('YlOrRd').copy()
    cmap.set_bad('#d9d9d9')
    with plt.rc_context({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'], 'axes.unicode_minus':False}):
        fig, ax = plt.subplots(figsize=(12,6))
        # 保持原图全体非空比率的色阶上限，以便修订前后直接比较。
        im = ax.imshow(data, aspect='auto', cmap=cmap, vmin=0, vmax=float(rates.max().max()*100))
        ax.set_xticks(range(24)); ax.set_yticks(range(12), range(1,13))
        ax.set_xlabel('起飞机场本地计划起飞小时'); ax.set_ylabel('月份')
        ax.set_title('哪些月份和本地起飞时段延误率较高？', pad=36)
        fig.colorbar(im, ax=ax, label='到达延误率（%）')
        ax.legend(handles=[Patch(facecolor='#d9d9d9', label='灰色：有效到达n<100或无有效数据；格内标注n')],
                  loc='lower left', bbox_to_anchor=(0,1.01), frameon=False, fontsize=9)
        for row,col in zip(*np.where(mask.to_numpy())):
            n=counts.iloc[row,col]
            ax.text(col,row,'无数据' if pd.isna(n) else f'n={int(n)}',ha='center',va='center',fontsize=6.5,color='#303030')
        note=('范围：2024年BTS报送航班；来源：BTS；n为未取消、未备降且到达标签和分钟数有效的航班数。\n'
              'n<100的格子灰显，不按延误率着色；100为本次选定的展示门槛，非老师规定或统计显著性标准。\n'
              '灰色不表示零延误；完整比率及分母仍保留于month_hour.csv。n≥100也不保证规律稳定。')
        fig.text(.02,.015,note,fontsize=8,color='#444444')
        fig.tight_layout(rect=[0,.12,1,1])
        fig.savefig(output,dpi=170)
        plt.close(fig)
    return [{'month':int(r+1),'hour':int(c),'valid_arrivals':None if pd.isna(counts.iloc[r,c]) else int(counts.iloc[r,c])} for r,c in zip(*np.where(mask.to_numpy()))]

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    table=pd.read_csv(root/'tables/month_hour.csv')
    masked=plot_month_hour(table,root/'figures/03_month_hour.png')
    print(f'重绘完成：{len(masked)}/288个格子灰显；统计表未修改。')
