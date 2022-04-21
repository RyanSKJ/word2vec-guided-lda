# word2vec-guided-lda
|word2vec-lda算法的文本生成过程 |
|:----|
|输入：文档集合  <br> 输出：文档-主题分布$\theta$和主题-词分布$\phi$|
| 1：选择表示文档中各主题的概率分布 $\theta$，$\theta$\~*Dir*($\alpha$) <br> 2：从概率分布$\theta$中选择一个主题*z* <br> 3：生成一个主题-词概率分布$\phi$<sub>*l*</sub>，$\phi$<sub>*l*</sub>\~*Dir*($\beta$) <br> 4：通过*word2vec*模型引导生成一个主题-词概率分布$\phi$<sub>*word2vec*</sub> <br> 5：通过公式 $\phi=\lambda\phi$<sub>*l*</sub> + $(1-\lambda)\phi$<sub>*word2vec*</sub> 生成综合的主题-词概率分布 $\phi$ <br> 6：从概率分布$\phi$中选择一个主题为z的词语|
