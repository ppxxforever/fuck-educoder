from PIL import Image
import numpy as np
import os
from sklearn.mixture import GaussianMixture

#******** Begin *********#
img = np.array(Image.open('./step3/image/test.jpg').convert('RGB'))
h, w, _ = img.shape
data = img.reshape(-1, 3).astype(np.float64)

gmm = GaussianMixture(n_components=3, random_state=0)
labels = gmm.fit_predict(data)

rows = np.repeat(np.arange(h).reshape(-1, 1), w, axis=1).reshape(-1)
mean_row = [rows[labels == k].mean() if np.any(labels == k) else 0 for k in range(3)]
sky = int(np.argmin(mean_row))
road = int(np.argmax(mean_row))
veg = 3 - sky - road

lut = np.zeros((3, 3), dtype=np.uint8)
lut[road] = (255, 255, 0)
lut[sky] = (0, 0, 255)
lut[veg] = (0, 255, 0)

result = lut[labels].reshape(h, w, 3)
os.makedirs('./step3/dump', exist_ok=True)
Image.fromarray(result.astype('uint8')).save('./step3/dump/result.jpg')
#********* End *********#