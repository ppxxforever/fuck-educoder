from PIL import Image
import numpy as np
import os
from sklearn.mixture import GaussianMixture

#******** Begin *********#
base_dir = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(base_dir, 'image', 'test.jpg')
dump_dir = os.path.join(base_dir, 'dump')
save_path = os.path.join(dump_dir, 'result.jpg')

img = np.array(Image.open(image_path).convert('RGB'))
h, w, _ = img.shape
data = img.reshape(-1, 3)

gmm = GaussianMixture(n_components=3, random_state=0)
gmm.fit(data)

batch_size = 50000
labels = np.empty(data.shape[0], dtype=np.int32)
for start in range(0, data.shape[0], batch_size):
    end = min(start + batch_size, data.shape[0])
    labels[start:end] = gmm.predict(data[start:end])

color_map = np.array([[255, 255, 0], [0, 0, 255], [0, 255, 0]], dtype=np.uint8)
result = color_map[labels].reshape(h, w, 3)

os.makedirs(dump_dir, exist_ok=True)
Image.fromarray(result).save(save_path)
#********* End *********#