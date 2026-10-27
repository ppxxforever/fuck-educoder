#导入第三方包-词云
from wordcloud import WordCloud

#导入第三方包-绘图
import matplotlib.pyplot as plt

#导入第三方包-结巴分词
import jieba

#设置文本文件路径
path = 'myworld.txt'
#读文本文件
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 结巴分词，生成字符串，对分词结果以空格隔开
cut_text = ' '.join(jieba.cut(text))

#设置字体（仿宋）font_path="simfang.ttf"，背景颜色（白色），词云宽高
wordcloud = WordCloud(font_path="simfang.ttf", background_color="white", width=1000, height=880)

# 绘制词云图
wordcloud.generate(cut_text)
plt.imshow(wordcloud, interpolation="bilinear")

# 关闭坐标显示
plt.axis("off")

#**************End***********#
# 显示图形
#plt.show()
#保存图形
wordcloud.to_file("t0804/result/tu4.png")