# -*- coding: utf-8 -*-
import sys
from sklearn.datasets import make_blobs
from sklearn.neighbors import KNeighborsClassifier

tokens = sys.stdin.read().strip().split()
if tokens:
    for i in range(0, len(tokens), 4):
        samples = int(tokens[i])
        random_state = int(tokens[i+1])
        x1 = float(tokens[i+2])
        x2 = float(tokens[i+3])

        X, y = make_blobs(n_samples=samples, random_state=random_state)
        clf = KNeighborsClassifier()
        clf.fit(X, y)
        print(clf.predict([[x1, x2]]).tolist())