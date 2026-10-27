#encoding=utf8
from sklearn.cluster import KMeans
import numpy as np

def kmeans_cluster(data):
    '''
    input:data(ndarray):样本数据
    output:result(ndarray):聚类结果
    '''
    #********* Begin *********#
    kmeans = KMeans(n_clusters=3, random_state=0, n_init=10)
    labels = kmeans.fit_predict(data)
    order = np.argsort(kmeans.cluster_centers_[:, 6])[::-1]
    mapping = {old: new for new, old in enumerate(order)}
    result = np.array([mapping[label] for label in labels])
    #********* End *********# 
    return result