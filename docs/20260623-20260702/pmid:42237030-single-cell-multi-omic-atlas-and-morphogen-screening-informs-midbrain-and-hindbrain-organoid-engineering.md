---
title: Single-cell multi-omic atlas and morphogen screening informs midbrain and hindbrain organoid engineering.
title_zh: 单细胞多组学图谱与形态发生因子筛选助力中脑与后脑类器官工程构建
authors: "Nadezhda Azbukina, Zhisong He, Hsiu-Chuan Lin, Malgorzata Santel, Bijan Kashanian, Ashley Maynard, Tivadar Török, Ryoko Okamoto, Marina T Nikolova, Makiko Seimiya, Sabina Kanton, Valentin Brösamle, Rene Holtackers, J Gray Camp, Barbara Treutlein"
date: 2026-06-03
pdf: "https://pubmed.ncbi.nlm.nih.gov/42237030/"
tags: ["query:neural-organoid"]
score: 9.0
evidence: 中脑与后脑类器官工程的单细胞多组学图谱
tldr: 中脑和后脑的神经管分区涉及运动、感觉与认知功能，其发育机制与类器官建模仍待完善。作者利用配对的单细胞转录组与染色质可及性测序，绘制中脑和后脑类器官的细胞组成与调控网络图谱，并结合转录因子扰动解析神经元分化机制。进一步通过单细胞多重形态发生素筛选，发现能拓展现有模型的新条件，生成延髓甘氨酸能神经元和小脑谷氨酸能神经元亚型。该多组学图谱与筛选揭示了形态发生素与调控子关系，指导区域特异性祖细胞向后脑多种神经元类型分化，为类器官工程提供了理论与实验依据。
source: pubmed
selection_source: fresh_fetch
motivation: 现有中脑/后脑类器官细胞组成与调控机制不明，限制了其在发育研究和疾病建模中的应用。
method: 采用配对单细胞转录组与ATAC测序构建多组学图谱，结合基因调控网络推断、转录因子扰动及多重形态发生素筛选。
result: 发现现有类器官含腹侧与背侧多种细胞类型，筛选出可生成延髓甘氨酸能与小脑谷氨酸能神经元的新形态发生素条件。
conclusion: 多组学图谱与形态发生素筛选揭示了调控区域特异性神经元分化的形态发生素-调控子机制，助力类器官工程优化。
---

## 摘要
神经管的模式化过程建立了协调运动、处理感觉输入并整合认知功能的中脑与后脑结构。这些结构中的细胞损伤是多种神经系统疾病的病因，体外类器官模型有望为理解发育过程和构建疾病模型提供新途径。在本研究中，我们利用配对的单细胞转录组和染色质可及性测序，绘制了中脑与后脑类器官模型中的细胞组成与调控机制图谱。我们发现，现有的中脑类器官方案能够生成腹侧与背侧细胞类型，覆盖包括底板、背侧与腹侧中脑以及相邻后脑区域在内的多个区域。基因调控网络推断与转录因子扰动实验揭示了神经元分化背后的机制。一项单细胞多重模式化筛选鉴定出能够扩展现有类器官模型的形态发生因子浓度组合，其中包括生成延髓甘氨酸能神经元和小脑谷氨酸能亚型的条件。综上，该多组学图谱与形态发生因子筛选揭示了指导后脑各区域特异性祖细胞向多种神经元类型分化的形态发生因子—调控子（regulon）关系。

## Abstract
Patterning of the neural tube establishes midbrain and hindbrain structures that coordinate motor movement, process sensory input and integrate cognitive functions. Cellular impairment within these structures underlies diverse neurological disorders, and in vitro organoid models promise inroads to understanding development and modeling disease. Here, we use paired single-cell transcriptome and accessible chromatin sequencing to map cell composition and regulatory mechanisms in organoid models of midbrain and hindbrain. We find that existing midbrain organoid protocols generate ventral and dorsal cell types, covering regions including floor plate, dorsal and ventral midbrain and adjacent hindbrain regions. Gene regulatory network inference and transcription factor perturbation resolve mechanisms underlying neuronal differentiation. A single-cell multiplexed patterning screen identifies morphogen concentrations that expand existing organoid models, including conditions generating medulla glycinergic neurons and cerebellum glutamatergic subtypes. Together, the multi-omic atlas and morphogen screen reveal morphogen-regulon relationships guiding region-specific progenitor differentiation towards diverse neuron types of the posterior brain.

---

## 论文详细总结（自动生成）

# 论文总结：单细胞多组学图谱与形态发生因子筛选助力中脑与后脑类器官工程构建

## 1. 核心问题与研究背景

- **研究对象**：神经管的中脑（midbrain）与后脑（hindbrain）区域在发育过程中经历复杂的模式化（patterning），最终形成负责运动协调、感觉信息处理与认知整合的关键脑结构。
- **临床意义**：这些区域的细胞损伤与多种神经系统疾病（如帕金森病等中脑多巴胺能神经元相关疾病）密切相关，因此构建能够忠实还原体内发育过程的体外模型具有重要价值。
- **核心问题**：现有的中脑/后脑类器官方案虽已被广泛使用，但其**实际生成的细胞组成**（是否覆盖背侧/腹侧、是否包含相邻后脑区域）以及**驱动神经元分化的调控网络机制**尚不清楚，这限制了类器官作为发育模型和疾病模型的精细化应用。
- **整体含义**：通过绘制类器官的多组学图谱并系统筛选形态发生因子（morphogen）组合，论文试图建立"形态发生因子—基因调控子（regulon）—细胞类型"之间的因果链条，从而为理性设计新的类器官分化方案提供依据。

## 2. 方法论

- **核心思路**：将"图谱绘制（表征已有模型）"与"筛选优化（拓展新条件）"相结合的两阶段策略。
- **关键技术手段**：
  - **配对单细胞多组学测序**：对同一细胞同时进行转录组（scRNA-seq）与染色质可及性（scATAC-seq）测序，从而将基因表达变化与顺式调控元件的开放状态直接关联。
  - **基因调控网络（GRN）推断**：基于转录组与表观基因组的联合信息，推断转录因子（TF）与其下游靶基因构成的调控子（regulon），揭示驱动神经元谱系分化的调控逻辑。
  - **转录因子扰动实验**：通过对候选关键TF进行功能性扰动（过表达/敲低等），验证其在神经元分化中的因果作用，用以佐证GRN推断结果。
  - **单细胞多重形态发生因子筛选（multiplexed patterning screen）**：同时对多种形态发生因子（如SHH、WNT、FGF、BMP等信号通路激动剂/拮抗剂）在不同浓度组合下进行多路筛选，并用单细胞测序读出每种条件下产生的细胞类型，从而系统性建立形态发生因子浓度—细胞命运的映射关系。
- **说明**：论文未给出数学公式或算法伪代码，方法本质上是"实验+计算分析"流程（测序数据处理、聚类注释、GRN推断算法、扰动效应评估），属于生物信息学/发育生物学范式，而非机器学习模型训练范式。

## 3. 实验设计

- **模型/场景**：人多能干细胞（hiPSC）来源的中脑与后脑类器官，覆盖底板（floor plate）、背侧中脑、腹侧中脑及相邻后脑区域（如延髓、小脑）。
- **数据集类型**：自产的配对scRNA-seq + scATAC-seq数据集（图谱阶段），以及多重形态发生因子筛选阶段产生的单细胞组学数据（筛选阶段）。
- **对比/基准**：
  - 未与其他已发表类器官方案进行系统性横向对比（如未明确对标其他实验室的中脑类器官协议），而是以**体内发育参照图谱（如已知的胚胎神经管分区标志基因）**作为细胞类型注释和验证的"金标准"。
  - 通过转录因子扰动实验作为方法学内部的对照（扰动组 vs. 对照组），验证GRN推断的因果关系。
- **Benchmark 性质**：本质是探索性、描述性的发育生物学研究，其"benchmark"更多体现为与已知体内发育图谱的比对，而非机器学习意义上的标准数据集/指标对比。

## 4. 资源与算力

- 论文摘要及提供的元数据中**未提及任何计算硬件信息**（如GPU型号、数量、训练时长等）。
- 本研究属于湿实验（单细胞测序、类器官培养、分子生物学扰动实验）为主、生物信息学分析为辅的工作，通常主要计算资源集中在测序数据处理与统计分析（如CPU集群/云计算平台），而非深度学习训练意义上的GPU算力。
- **结论**：算力资源未在现有材料中说明，无法进一步总结。

## 5. 实验数量与充分性

- 从摘要及总结可推断，论文至少包含以下几类实验/分析模块：
  1. 中脑/后脑类器官的多组学图谱构建（转录组+染色质可及性联合分析）；
  2. 基因调控网络推断；
  3. 转录因子功能扰动验证（针对多个候选TF）；
  4. 单细胞多重形态发生因子筛选（涉及多种形态发生因子的浓度组合矩阵）。
- **充分性评估**：
  - 图谱构建覆盖了腹侧与背侧多个区域，说明细胞组成刻画较为全面；
  - 筛选阶段采用"多重"（multiplexed）设计，意味着同时测试了较多形态发生因子浓度组合，具有较高通量，但具体实验组数、重复次数、统计检验方法在摘要中未详细披露；
  - 由于缺乏与其他实验室已发表方案的直接横向对比，其"客观性/公平性"更多依赖于内部一致性验证（如扰动实验）与体内参照图谱比对，而非跨方法基准测试，这在方法学严谨性上略显不足，但符合该领域（发育生物学/类器官工程）常见的研究范式。

## 6. 主要结论与发现

- 现有中脑类器官方案实际上比预期生成了**更丰富的细胞类型**，涵盖底板、背侧与腹侧中脑，以及邻近的后脑区域，而不仅限于经典关注的中脑多巴胺能神经元。
- 通过GRN推断与TF扰动，揭示了驱动特定神经元亚型分化的调控机制。
- 多重形态发生因子筛选**成功鉴定出新的分化条件**，能够生成此前模型未覆盖的细胞类型，包括：
  - 延髓（medulla）甘氨酸能神经元；
  - 小脑（cerebellum）谷氨酸能神经元亚型。
- 综合图谱与筛选数据，建立了**形态发生因子—调控子（regulon）关系网络**，为理性设计后脑区域特异性神经元分化方案提供了机制性依据。

## 7. 优点与亮点

- **多组学联合分析**：转录组与染色质可及性配对测序提供了比单一组学更强的调控机制解析能力。
- **图谱+筛选的闭环设计**：先系统表征现有模型的"真实"细胞组成（往往超出研究者预期），再针对性地筛选新条件填补空白，体现了"发现问题—解决问题"的完整研究逻辑。
- **高通量筛选策略**：单细胞多重形态发生因子筛选能够在同一批次中并行评估多种信号通路组合，提高了筛选效率，是类器官工程领域较为前沿的方法学应用。
- **机制与应用并重**：不仅停留在细胞类型鉴定层面，还通过GRN推断和TF扰动深入到调控机制层面，增强了结论的因果性和可解释性。
- **应用价值明确**：新发现的分化条件（延髓甘氨酸能神经元、小脑谷氨酸能神经元）直接扩展了可用的类器官模型谱系，对神经退行性疾病、运动/感觉障碍等相关疾病建模具有潜在应用价值。

## 8. 不足与局限

- **算力与技术细节透明度不足**：摘要及提供材料未说明测序深度、样本量、生物学重复数、统计方法及计算资源，难以评估结果的统计效力和可重复性。
- **缺乏跨实验室横向对比**：未与其他已发表的中脑/后脑类器官方案进行系统比较，results的普适性和优越性有待进一步验证。
- **体外模型的固有局限**：类器官尽管能模拟部分体内发育过程，但仍难以完全复现体内环境的三维空间信号梯度、非神经细胞（如血管、免疫细胞）互作及长期成熟过程，因此其发现（如新细胞类型的产生）在多大程度上反映真实体内发育机制仍需体内实验（如动物模型）进一步验证。
- **筛选覆盖的完整性**：形态发生因子筛选虽为"多重"设计，但形态发生因子种类、浓度梯度组合的空间仍然有限，可能未能穷尽所有潜在的细胞命运决定条件，存在筛选"盲区"的风险。
- **偏差风险**：类器官起始的hiPSC系、培养条件等实验室特异性因素可能引入批次效应或系统性偏差，影响图谱结果在不同实验室间的可迁移性。
- **疾病建模验证的缺失**：论文虽强调类器官在疾病建模中的潜力，但摘要中未见具体疾病模型的验证数据，实际应用价值仍需后续研究补充。

（完）
