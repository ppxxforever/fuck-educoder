import torch


def rnn(input, state, params):
    """
    循环神经网络的前向传播
    :param input: 输入，形状为 [ batch_size,num_inputs ]
    :param state: 上一时刻循环神经网络的状态，形状为 [ batch_size,num_hiddens ]
    :param params: 循环神经网络的所使用的权重以及偏置
    :return: 输出结果和此时刻网络的状态
    """
    W_xh, W_hh, b_h, W_hq, b_q = params
    H = state
    ########## Begin ##########
    H = torch.tanh(torch.matmul(input, W_xh) + torch.matmul(H, W_hh) + b_h)
    Y = torch.matmul(H, W_hq) + b_q
    ########## End ##########
    return Y, H


def init_rnn_state(num_inputs, num_hiddens):
    """
    循环神经网络的初始状态的初始化
    :param num_inputs: 输入层中神经元的个数
    :param num_hiddens: 隐藏层中神经元的个数
    :return: 循环神经网络初始状态
    """
    ########## Begin ##########
    init_state = torch.zeros((num_inputs, num_hiddens))
    ########## End ##########
    return init_state