#encoding=utf8    
import numpy as np

def distance(x,y,p=2):
    '''
    input:x(ndarray):第一个样本的坐标
          y(ndarray):第二个样本的坐标
          p(int):等于1时为曼哈顿距离，等于2时为欧氏距离
    output:distance(float):x到y的距离      
    ''' 
    #********* Begin *********#
    if p == 1:
        return float(np.sum(np.abs(x - y)))
    elif p == 2:
        return float(np.sqrt(np.sum(np.square(x - y))))
    else:
        return float(np.linalg.norm(x - y, ord=p))
    #********* End *********#