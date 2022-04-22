# 1.模型
![image](https://github.com/RyanSKJ/word2vec-guided-lda/blob/master/word2vec_lda_model.png)
|word2vec-lda算法的文本生成过程 |
|:----|
|输入：文档集合  <br> 输出：文档-主题分布 ![](http://latex.codecogs.com/svg.latex?\theta) 和主题-词分布 ![](http://latex.codecogs.com/svg.latex?\phi)|
| 1：选择表示文档中各主题的概率分布 ![](http://latex.codecogs.com/svg.latex?\theta)，![](http://latex.codecogs.com/svg.latex?\theta)\~*Dir*(![](http://latex.codecogs.com/svg.latex?\alpha)) <br> 2：从概率分布![](http://latex.codecogs.com/svg.latex?\theta)中选择一个主题 *z* <br> 3：生成一个主题-词概率分布![](http://latex.codecogs.com/svg.latex?\phi)<sub>*l*</sub>，![](http://latex.codecogs.com/svg.latex?\phi)<sub>*l*</sub>\~*Dir*(![](http://latex.codecogs.com/svg.latex?\beta)) <br> 4：通过*word2vec*模型引导生成一个主题-词概率分布![](http://latex.codecogs.com/svg.latex?\phi)<sub>*word2vec*</sub> <br> 5：通过公式 ![](http://latex.codecogs.com/svg.latex?\phi=\lambda_{1}\phi_{l}+\lambda_{2}\phi_{word2vec}) 生成综合的主题-词概率分布 ![](http://latex.codecogs.com/svg.latex?\phi) <br> 6：从概率分布 ![](http://latex.codecogs.com/svg.latex?\phi)中选择一个主题为 *z* 的词语|
# 2.结果
![image](https://github.com/RyanSKJ/word2vec-guided-lda/blob/master/perplexity.png)
![image](https://github.com/RyanSKJ/word2vec-guided-lda/blob/master/coherence.png)
![image](https://github.com/RyanSKJ/word2vec-guided-lda/blob/master/result.png)
