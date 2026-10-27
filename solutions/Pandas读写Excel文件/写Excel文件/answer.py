# 导入pandas库
import pandas as pd

# 嵌套字典
dct = {
    'ID': {0: 20, 1: 40, 2: 10},
    'Name': {0: '陈芳', 1: '刘佳', 2: '方一鸣'},
    'Marks': {0: 85, 1: 92, 2: 65},
    'Grade': {0: 'B', 1: 'A', 2: 'D'}
}

# 创建DF对象
df = pd.DataFrame(dct)

# 写入Excel文件中
df.to_excel('grade.xlsx')