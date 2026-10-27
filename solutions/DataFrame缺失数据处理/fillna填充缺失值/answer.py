import pandas as pd
import numpy as np

# 创建对象data
data=pd.DataFrame({'a':[1,2,3,np.nan,np.nan],
                   'b':[np.nan,3,np.nan,4,np.nan],
                   'c':[np.nan,4,np.nan,0,np.nan]})

# 用data均值填充对象data中的缺失值
data = data.fillna(data.mean())

print(data)