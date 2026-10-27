# 导入pandas库
import pandas as pd

# 导入numpy库
import numpy as np

# 创建对象
data=pd.DataFrame({'a':[1,2,3,np.nan,np.nan],
                    'b':[np.nan,3,np.nan,4,np.nan],
                    'c':[np.nan,4,np.nan,0,np.nan]})

# 删除缺失值行，返回新对象
data = data.dropna()

print(data)