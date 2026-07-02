---
title: SPACE-seq integrates spatial transcriptomics and lineage tracing in native tissues.
title_zh: SPACE-seq：在天然组织中整合空间转录组学与谱系追踪
authors: "Yuemeng Jia, Dawei Sun, Jackson A Weir, Xugeng Liu, Andrew J C Russell, YeEun Kim, Nicholas Thom, Giovanni Marrero, Vipin Kumar, Fei Chen, Fernando D Camargo"
date: 2026-06-09
pdf: "https://pubmed.ncbi.nlm.nih.gov/42263684/"
tags: ["query:sc-neuro-bioinfo"]
score: 6.0
evidence: 空间转录组学结合CRISPR谱系追踪解析细胞状态与组织结构
tldr: 理解细胞如何转变状态、与邻居互作并组织成组织，需要在原生空间背景下记录细胞谱系历史，但现有方法难以同时兼顾谱系、状态与空间信息。作者开发SPACE-seq，将CRISPR谱系条形码记录与slide-seq空间转录组学结合，实现近单细胞分辨率下谱系、细胞状态与组织结构的联合解析。应用于肿瘤模型，发现克隆相关细胞间存在转录多样化及肿瘤-基质相互塑造的串扰并加以实验验证；在肝脏发育中揭示成肝细胞在特定窗口期扩散形成预示肝小叶结构的空间谱系区室。该平台具有广泛适用性，为揭示细胞组织、谱系动态与组织构建原理提供了新工具。
source: pubmed
selection_source: fresh_fetch
motivation: 现有技术难以在原生组织空间背景下同时记录细胞谱系历史、细胞状态及其相互作用。
method: 开发SPACE-seq平台，将CRISPR谱系条形码记录与slide-seq空间转录组学整合，近单细胞分辨率联合解析谱系、状态与组织结构。
result: 发现肿瘤内克隆细胞转录多样化及肿瘤-基质相互塑造的串扰，并揭示肝母细胞扩散窗口期形成预示肝叶结构的谱系区室。
conclusion: SPACE-seq具备广泛适应性，可揭示疾病与发育中此前难以触及的细胞组织与谱系动态规律。
---

## 摘要
理解细胞如何改变状态、与邻近细胞相互作用并组织成组织，需要在天然空间背景下记录细胞谱系历史。在此，我们提出了SPACE-seq（一种通过基于CRISPR的条形码与slide-seq实现的空间谱系追踪平台），这是一种多功能平台，将基于CRISPR的谱系记录与空间转录组学相结合，在原位以近单细胞分辨率联合解析谱系、细胞状态和组织结构。利用SPACE-seq，我们揭示了克隆相关细胞间的肿瘤内转录多样化，并鉴定出肿瘤-基质间的相互串扰，这种串扰会相互重塑恶性细胞群和基质细胞群的行为，我们通过实验进一步验证了这一发现。除疾病研究外，SPACE-seq还揭示了一个狭窄的发育窗口期，在此期间肝母细胞的分散有助于形成空间上受限的谱系区室，这些区室预示了肝脏叶状结构的形成。综上所述，这些结果凸显了SPACE-seq在揭示此前难以触及的细胞组织、谱系动态和组织模式形成原理方面的广泛适用性和灵活性。

## Abstract
Understanding how cells change state, interact with their neighbors, and organize into tissues requires recording of cellular lineage history in native spatial context. Here, we present SPACE-seq (spatial tracing enabled by CRISPR-based barcodes and slide-seq), a versatile platform that integrates CRISPR-based lineage recording with spatial transcriptomics to jointly resolve lineage, cell state, and tissue architecture at near-cellular resolution in situ. Using SPACE-seq, we uncovered intratumor transcriptional diversification among clonally related cells and identified tumor-stroma crosstalk that reciprocally reshapes behaviors of both malignant and stromal populations, which we further experimentally validated. Beyond disease, SPACE-seq revealed a narrow developmental window in which hepatoblast dispersion contributes to spatially confined lineage compartments that prefigure liver lobar architecture. Together, these results highlight the broad applicability and adaptability of SPACE-seq to uncover previously inaccessible principles of cellular organization, lineage dynamics, and tissue patterning.