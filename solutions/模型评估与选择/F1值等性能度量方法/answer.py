import numpy as np


ndarray = np.ndarray


def task(y_true: ndarray, y_pred: ndarray):
    
    '''
    二分类任务，正标签为1，负标签为0
    y_true: 数组1*n, 真实标签
    y_pred: 数组1*n, 预测标签
    '''

    TP = sum((y_pred==1)==(y_pred==y_true))
    FP = sum((y_pred==1)==(y_pred!=y_true))
    FN = sum((y_pred==0)==(y_pred!=y_true))
    TN = sum((y_pred==0)==(y_pred==y_true))
    
    precision = TP / (TP + FP)
    
    '''
    任务描述：根据公式实现查全率(recall)和F1
    '''
    ########## Begin ##########
    TP = sum((y_pred==1)==(y_pred==y_true))
    FP = sum((y_pred==1)==(y_pred!=y_true))
    FN = sum((y_pred==0)==(y_pred!=y_true))
    TN = sum((y_pred==0)==(y_pred==y_true))

    precision = TP / (TP + FP)

    ########### Begin ##########
    # 计算查全率 recall
    recall = TP / (TP + FN)
    F1 = 2 * precision * recall / (precision + recall)
    return precision, recall, F1
    ########## End ##########
    
    return precision, recall, f1_score