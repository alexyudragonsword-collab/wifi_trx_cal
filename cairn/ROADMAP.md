# wifitrx 路线图

**当前焦点**:交付收尾——功能主线已落地,2026-09-08 工程体检的 P0/P1 整改完成
(版本号见 `docs/backlog_zh.md` 头部,本文不再抄版本号),等待两项外部输入。

## 里程碑

- [ ] A2:链路仿真组各 MCS PER 门限到货,替换 `link/mcs.py` 的 `snr_req_db` 估计值(影响交付数字的唯一未完成项)。
- [ ] A4:电路组逐档基带噪声表到货,`noise_v_sqrthz` 升级为按 VGA 档查表(同批替换两个占位参数)。

> 工程待办的唯一权威来源是 `docs/backlog_zh.md`(头部"当前状态"块);本文件只做粗粒度镜像,不一致时以 backlog 为准。

## 开放问题

0. ~~`EvmBudget.cpe_tracked_fraction` 默认 0.5 vs 实算~~ 已裁决(0.7.9):默认改为按谱与符号长度现算,见 `docs/backlog_zh.md` B15 末尾。
1. 远期边界项(真实温度动力学、谐波混频、MIMO 频变互耦、DAC/ADC 镜像等)是否排期,待交付后由使用方反馈决定——清单见规格书 §9 / 教程 ch9。
2. 体检 P2(择期):传播信道(现为传导模式)、OFDMA/打孔/空音、AGC 建立动态、`tx_iq` 多音合并、`tutorial.html` 改 CI 产物——见体检报告与 `docs/backlog_zh.md` B16–B21。

## 知识专题文档

- `cairn/相噪与CPE去除.md`——相噪经 CPE 去除的物理结论与被推翻的判断。
- `cairn/Android出货线.md`——Chaquopy 出货线的裁决协议与"构建绿但端上错"的根因清单。
- `cairn/守卫有效性.md`——守卫的四种失效形态(空转/错靶/恒红/被遮)、双向验证规程与案例台账。
