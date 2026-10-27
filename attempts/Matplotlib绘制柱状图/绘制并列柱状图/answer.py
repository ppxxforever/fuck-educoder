import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

base_dir = os.path.dirname(os.path.abspath(__file__))
filename = 'temperature.txt'
cwd = os.getcwd()

candidates = []
for d in [base_dir, os.path.dirname(base_dir), os.path.dirname(os.path.dirname(base_dir)), cwd, os.path.join(cwd, 'bar2'), os.path.join(os.path.dirname(base_dir), 'bar2')]:
    if d:
        candidates.append(os.path.join(d, filename))
        candidates.append(os.path.join(d, 'data', filename))
candidates.append('/data/workspace/myshixun/temperature.txt')
candidates.append('/data/workspace/myshixun/bar2/temperature.txt')

data_path = None
for p in candidates:
    if os.path.isfile(p):
        data_path = p
        break

if data_path is None:
    roots = [base_dir, os.path.dirname(base_dir), cwd]
    checked_roots = set()
    for root in roots:
        if not root or not os.path.isdir(root) or root in checked_roots:
            continue
        checked_roots.add(root)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in ('result', '.git', '__pycache__', '.ipynb_checkpoints')]
            if filename in filenames:
                data_path = os.path.join(dirpath, filename)
                break
        if data_path:
            break

if data_path is None:
    data_path = os.path.join(base_dir, filename)

df = None
for enc in ['utf-8', 'gbk', 'utf-8-sig']:
    try:
        raw = pd.read_csv(data_path, sep='\t', encoding=enc, header=None)
        raw = raw.dropna(axis=1, how='all')
        if raw.shape[1] < 3:
            continue
        raw = raw.iloc[:, :3]
        raw = raw.dropna(how='all')
        if raw.shape[0] == 0:
            continue
        first = [str(v).strip().replace('\ufeff', '') for v in raw.iloc[0].tolist()]
        is_header = False
        if len(first) >= 3:
            if ('城市' in first[0]) or ('最高温度' in first[1]) or ('最低温度' in first[2]) or ('最高' in first[1]):
                is_header = True
        if is_header:
            raw = raw.iloc[1:].reset_index(drop=True)
        if raw.shape[0] == 0:
            continue
        raw.columns = ['城市', '最高温度', '最低温度']
        df = raw
        break
    except Exception:
        continue

if df is None:
    for enc in ['utf-8', 'gbk', 'utf-8-sig']:
        try:
            tmp = pd.read_csv(data_path, sep='\t', encoding=enc)
            tmp = tmp.dropna(axis=1, how='all')
            if tmp.shape[1] >= 3:
                tmp = tmp.iloc[:, :3]
                if '城市' not in tmp.columns:
                    tmp.columns = ['城市', '最高温度', '最低温度']
                df = tmp
                break
        except Exception:
            continue

if df is None:
    raise FileNotFoundError(data_path)

df = df.dropna(subset=['城市', '最高温度', '最低温度'])
df['城市'] = df['城市'].astype(str).str.strip()
df = df[df['城市'] != '']
df = df[df['城市'].str.lower() != 'nan']

high = pd.to_numeric(
    df['最高温度'].astype(str).str.replace('℃', '').str.replace('°C', '').str.replace('°c', '').str.strip(),
    errors='coerce'
)
low = pd.to_numeric(
    df['最低温度'].astype(str).str.replace('℃', '').str.replace('°C', '').str.replace('°c', '').str.strip(),
    errors='coerce'
)

df = df.assign(high=high, low=low).dropna(subset=['high', 'low'])

city = df['城市'].tolist()
high = df['high'].astype(float).tolist()
low = df['low'].astype(float).tolist()

x = np.arange(len(city))
width = 0.4

plt.bar(x - width / 2, high, width=width, label='最高温度')
plt.bar(x + width / 2, low, width=width, label='最低温度')

plt.xticks(x, city)
plt.ylim(0, 40)
plt.legend()

result_dir = os.path.join(base_dir, 'result')
os.makedirs(result_dir, exist_ok=True)
plt.savefig(os.path.join(result_dir, 'tu2.png'))
plt.close()