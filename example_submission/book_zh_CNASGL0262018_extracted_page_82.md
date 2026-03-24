- EUT 与频谱分析仪之间的链路 S 参数 0.724(m), 损耗 2.8dB(d)

则

$$
u _ { \mathrm { EUT-功分器 } } = { \frac { 0 . 7 \times 0 . 0 9 9 \times 1 0 0 } { { \sqrt { 2 } } \times 1 1 . 5 } } = 0 . 4 2 6 \mathrm { d B }
$$

$$
u _ {功分器-衰减网络} = { \frac { 0 . 0 9 9 \times 0 . 3 3 3 \times 1 0 0 } { { \sqrt { 2 } } \times 1 1 . 5 } } = 0.203 \mathrm { d B }
$$

$$
u _ {衰减网络-频谱仪 } = \frac { 0 . 3 3 3 \times 0 . 0 9 1 \times 1 0 0 } { \sqrt { 2 } \times 1 1 . 5 } = 0 . 1 8 6 \mathrm { d B }
$$

$$
u _ \mathrm{EUT-衰减网络} = \frac { 0.7 \times0.333\times 0.912 \times 0.912\times 100 } { \sqrt { 2 } \times 1 1 . 5 } = 1.192 \mathrm { d B}
$$

$$
u _ \mathrm{功分器-频谱仪} = \frac { 0.099\times0.333\times 0.794 \times 0.794\times 100 } { \sqrt { 2 } \times 1 1 . 5 } = 0.128 \mathrm { d B }
$$

$$
u _ \mathrm{EUT-频谱仪} = \frac { 0.7\times0.091\times 0.724 \times 0.724\times 100 } { \sqrt { 2 } \times 11.5 } = 0.205 \mathrm { dB }
$$

则 $u(\delta P_{M}) = \sqrt{0.426^2 + 0.203^2 + 0.186^2 + 1.192^2 + 0.128^2 + 0.205^2} = 1.318\,\mathrm{dB}$

5.5.3.5 被测样供电电压变化引入的不确定度分量$u(\delta P_v)$

在测试期间，实验室供电电压可控范围为0.1V，根据ETSI TR 100 028 表F.1

- 均值 $10\%(p)/V$
- 标准差 $3\%(p)/V$

$$
u \big ( \delta P _ { T } \big ) = = \frac { 0 . 1 V \times \sqrt { \big ( 10\% / V \big ) ^ { 2 } + \big ( 3\% / V \big ) ^ { 2 } } } { \sqrt { 3 } \times 2 3 . 0 } = 0 . 0 2 6 \mathrm { d B }
$$

5.5.3.6 时间周期变化引入的不确定度分量$u(\delta P_D)$

根据 ETSI TR 100 028 表 F.1, 时间周期误差为 $2\%(d)(p)(\sigma)$

$$
u ( \delta P _ { D } ) = = \frac { 2 \%} { 23.0 } = 0.087\mathrm { d B }
$$

# 5.5.4 不确定度概算

<table><tr><td>分量</td><td>概率分布</td><td>灵敏系数</td><td>不确定度分量值（dB）</td></tr></table>
