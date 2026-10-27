#encoding=utf8
import torch
import torch.nn as nn
from torch.autograd import Variable
import torch.utils.data as Data
import torchvision
import os
if os.path.exists('./step3/cnn.pkl'):
    os.remove('./step3/cnn.pkl')
    
#加载数据            
train_data = torchvision.datasets.MNIST(
    root='./step3/mnist/',
    train=True,                                       # this is training data
    transform=torchvision.transforms.ToTensor(),    # Converts a PIL.Image or numpy.ndarray to                        
    download=False,
)
#取6000个样本为训练集
train_data_tiny = []
for i in range(6000):
    train_data_tiny.append(train_data[i])
train_data = train_data_tiny
#********* Begin *********#
class CNN(nn.Module):
    def __init__(self):
        super(CNN, self).__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool2d(2)
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.MaxPool2d(2)
        )
        self.out = nn.Linear(32 * 7 * 7, 10)
    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = x.view(x.size(0), -1)
        out = self.out(x)
        return out

cnn = CNN()
train_loader = Data.DataLoader(dataset=train_data, batch_size=64, shuffle=True)
loss_func = nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(cnn.parameters(), lr=0.001)

for epoch in range(3):
    for step, (batch_x, batch_y) in enumerate(train_loader):
        batch_x = Variable(batch_x)
        batch_y = Variable(batch_y)
        outputs = cnn(batch_x)
        loss = loss_func(outputs, batch_y)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()


#********* End *********#
#保存模型
torch.save(cnn.state_dict(), './step3/cnn.pkl')