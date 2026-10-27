#********* Begin *********#
import os
import pandas as pd
from sklearn.tree import DecisionTreeClassifier

base_dir = os.path.dirname(os.path.abspath(__file__))

train_data = pd.read_csv(os.path.join(base_dir, 'train_data.csv')).values
label_df = pd.read_csv(os.path.join(base_dir, 'train_label.csv'))
label_columns = label_df.columns.tolist()
train_label = label_df.iloc[:, 0].values
test_data = pd.read_csv(os.path.join(base_dir, 'test_data.csv')).values

clf = DecisionTreeClassifier(criterion='gini', max_depth=5, random_state=0)
clf.fit(train_data, train_label)
pred = clf.predict(test_data)

pd.DataFrame(pred, columns=label_columns).to_csv(os.path.join(base_dir, 'predict.csv'), index=False)
#********* End *********#