from sklearn.metrics.cluster import fowlkes_mallows_score, adjusted_rand_score

def cluster_performance(y_true, y_pred):
    '''
    Return FM index and Rand index.
    :param y_true: reference cluster labels, ndarray
    :param y_pred: predicted cluster labels, ndarray
    :return: FM index, Rand index
    '''
    #********* Begin *********#
    fm = fowlkes_mallows_score(y_true, y_pred)
    rand = adjusted_rand_score(y_true, y_pred)
    return fm, rand
    #********* End *********#