#********* Begin *********#
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

def _read_csv_with_header_detection(path):
    first = pd.read_csv(path, header=None, nrows=1)
    try:
        float(first.iloc[0, 0])
        header = None
    except (ValueError, TypeError):
        header = 0
    df = pd.read_csv(path, header=header)
    return df.values, df.columns.tolist() if header == 0 else None

train_data, _ = _read_csv_with_header_detection('./step7/train_data.csv')
train_label, label_cols = _read_csv_with_header_detection('./step7/train_label.csv')
train_label = train_label.ravel()
test_data, _ = _read_csv_with_header_detection('./step7/test_data.csv')

clf = DecisionTreeClassifier()
clf.fit(train_data, train_label)
pred = clf.predict(test_data)

result = pd.DataFrame(pred, columns=label_cols if label_cols is not None else None)
result.to_csv('./step7/predict.csv', index=False, header=label_cols is not None)
#********* End *********#