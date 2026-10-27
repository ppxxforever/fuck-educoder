import numpy as np
from scipy import stats


def em_single(init_values, observations):
    """
    模拟抛掷硬币实验并估计在一次迭代中，硬币A与硬币B正面朝上的概率
    :param init_values:硬币A与硬币B正面朝上的概率的初始值，类型为list，如[0.2, 0.7]代表硬币A正面朝上的概率为0.2，硬币B正面朝上的概率为0.7。
    :param observations:抛掷硬币的实验结果记录，类型为list。
    :return:将估计出来的硬币A和硬币B正面朝上的概率组成list返回。如[0.4, 0.6]表示你认为硬币A正面朝上的概率为0.4，硬币B正面朝上的概率为0.6。
    """

    #********* Begin *********#
    observations = np.array(observations)
    counts = {'A': {'H': 0, 'T': 0}, 'B': {'H': 0, 'T': 0}}
    theta_A = init_values[0]
    theta_B = init_values[1]

    # E 步：按二项分布算每个样本来自 A / B 的权重
    for observation in observations:
        len_observation = len(observation)
        num_heads = observation.sum()
        num_tails = len_observation - num_heads
        contribution_A = stats.binom.pmf(num_heads, len_observation, theta_A)
        contribution_B = stats.binom.pmf(num_heads, len_observation, theta_B)
        weight_A = contribution_A / (contribution_A + contribution_B)
        weight_B = contribution_B / (contribution_A + contribution_B)
        counts['A']['H'] += weight_A * num_heads
        counts['A']['T'] += weight_A * num_tails
        counts['B']['H'] += weight_B * num_heads
        counts['B']['T'] += weight_B * num_tails

    # M 步：用期望计数重估参数
    new_theta_A = counts['A']['H'] / (counts['A']['H'] + counts['A']['T'])
    new_theta_B = counts['B']['H'] / (counts['B']['H'] + counts['B']['T'])
    return [new_theta_A, new_theta_B]
    #********* End *********#