# 导入pandas库
import pandas as pd

# 创建2行2列对象
df1=pd.DataFrame([[1,2],[3,4]])
# 创建3行3列对象
df2=pd.DataFrame([[6,6,6],[7,8,9],[0,0,0]])
#输出df1和df2
print(df1)
print(df2)


# 纵向合并df1和df2，并输出结果
vertical_concat = pd.concat([df1, df2], axis=0)
print("纵向合并：")
print(vertical_concat)


# 横向合并df1和df2，并输出结果
horizontal_concat = pd.concat([df1, df2], axis=1)
print("横向合并：")
print(horizontal_concat)