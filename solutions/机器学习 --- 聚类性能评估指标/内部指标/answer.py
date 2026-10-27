# -*- coding: utf-8 -*-
import numpy as np

def calc_DBI(feature, pred):
    '''
    计算并返回DB指数
    :param feature: 待聚类数据的特征，类型为`ndarray`
    :param pred: 聚类后数据所对应的簇，类型为`ndarray`
    :return: DB指数
    '''

    #********* Begin *********#
    feature = np.array(feature)
    pred = np.array(pred)
    clusters = np.unique(pred)

    centroids = {}
    avg_dists = {}
    for c in clusters:
        points = feature[pred == c]
        centroid = np.mean(points, axis=0)
        centroids[c] = centroid
        avg_dists[c] = np.mean([np.linalg.norm(p - centroid) for p in points])

    db = 0.0
    for i in clusters:
        worst = 0.0
        for j in clusters:
            if i == j:
                continue
            value = (avg_dists[i] + avg_dists[j]) / np.linalg.norm(centroids[i] - centroids[j])
            if value > worst:
                worst = value
        db += worst

    return float(db / len(clusters))
    #********* End *********#


def calc_DI(feature, pred):
    '''
    计算并返回Dunn指数
    :param feature: 待聚类数据的特征，类型为`ndarray`
    :param pred: 聚类后数据所对应的簇，类型为`ndarray`
    :return: Dunn指数
    '''

    #********* Begin *********#
    feature = np.array(feature)
    pred = np.array(pred)
    clusters = np.unique(pred)

    min_between = np.inf
    for i in range(len(clusters)):
        for j in range(i + 1, len(clusters)):
            points_i = feature[pred == clusters[i]]
            points_j = feature[pred == clusters[j]]
            for a in points_i:
                for b in points_j:
                    d = np.linalg.norm(a - b)
                    if d < min_between:
                        min_between = d

    max_within = 0.0
    for c in clusters:
        points = feature[pred == c]
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                d = np.linalg.norm(points[i] - points[j])
                if d > max_within:
                    max_within = d

    return float(min_between / max_within)
    #********* End *********#