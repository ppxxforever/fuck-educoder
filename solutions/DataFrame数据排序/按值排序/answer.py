import pandas as pd
import re


def read_temperature_data(path='temperature.txt'):
    encodings = ('utf-8-sig', 'gbk', 'gb18030', 'utf-8')
    lines = None
    for enc in encodings:
        try:
            with open(path, 'r', encoding=enc) as f:
                lines = f.readlines()
            break
        except UnicodeDecodeError:
            continue
    if lines is None:
        with open(path, 'r', encoding='latin1') as f:
            lines = f.readlines()

    records = []
    row_indexes = []

    for raw in lines:
        line = raw.strip().replace('\ufeff', '')
        if not line:
            continue
        if '最高温度' in line and '最低温度' in line:
            continue

        if ',' in line:
            parts = [p.strip() for p in line.split(',')]
        elif ';' in line:
            parts = [p.strip() for p in line.split(';')]
        elif '\t' in line:
            parts = [p.strip() for p in line.split('\t')]
        else:
            parts = re.split(r'\s+', line)

        parts = [p for p in parts if p != '']
        if not parts:
            continue

        idx = None
        if len(parts) >= 4 and re.match(r'^[-+]?\d+$', parts[0]):
            idx = int(parts[0])
            parts = parts[1:]

        if len(parts) < 3:
            continue

        city = parts[0]
        high = parts[1].replace('℃', '').replace('°C', '').strip()
        low = parts[2].replace('℃', '').replace('°C', '').strip()

        high = re.sub(r'[^0-9\-\.]', '', high)
        low = re.sub(r'[^0-9\-\.]', '', low)

        if high == '' or low == '':
            continue

        records.append((city, int(float(high)), int(float(low))))
        if idx is not None:
            row_indexes.append(idx)

    if row_indexes and len(row_indexes) == len(records):
        df = pd.DataFrame(records, columns=['城市', '最高温度', '最低温度'], index=row_indexes)
    else:
        df = pd.DataFrame(records, columns=['城市', '最高温度', '最低温度'])

    return df


df = read_temperature_data('temperature.txt')

df_sorted1 = df.sort_values(by='最高温度', ascending=True, kind='mergesort')
print(df_sorted1)

df_sorted2 = df.sort_values(by='最低温度', ascending=False, kind='mergesort')
df_sorted2 = df_sorted2.sort_values(by='最高温度', ascending=True, kind='mergesort')
print(df_sorted2)