import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd

plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False


def _resolve(name):
    """在当前目录、脚本所在目录及其父目录中查找文件。"""
    candidates = [name]
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(base, name))
        candidates.append(os.path.join(os.path.dirname(base), name))
    except NameError:
        pass
    candidates.append(os.path.join(os.getcwd(), name))
    for path in candidates:
        if os.path.exists(path):
            return path
    return name


def main():
    global plt
    # 兼容旧版本环境，确保 plt 已正确绑定
    try:
        plt
    except NameError:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.rcParams['font.sans-serif'] = ['SimHei']
        plt.rcParams['axes.unicode_minus'] = False

    data = pd.read_csv(_resolve('stock.csv'))
    high = data['high']
    low = data['low']

    plt.figure(figsize=(10, 5))
    plt.plot(high, label='最高价', marker='o')
    plt.plot(low, label='最低价', marker='*', linestyle=':')
    plt.legend()
    plt.title('某股票6月~7月的价格变化图', fontsize=20)
    plt.xlabel('日期', fontsize=14)
    plt.ylabel('元', fontsize=14)

    # 确保输出目录存在，并按测试脚本要求路径保存图像
    out_dir = os.path.dirname('Z2/result/tu2.png')
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir)
        except OSError:
            pass
    plt.savefig('Z2/result/tu2.png')
    plt.close()


main()