---
title: Co-expression-based models improve eQTL predictions for transcriptome-wide association studies and highlight new schizophrenia-associated genes.
title_zh: 基于共表达的模型改进转录组关联研究中的eQTL预测，并发现新的精神分裂症相关基因
authors: "Fabiana Rossi, Leonardo Sportelli, Gianluca C Kikidis, Giulia Grassi, Fabio Di Camillo, Alessandro Bertolino, Giuseppe Blasi, Christopher J Borcuk, Daniela Fusco, Thomas M Hyde, Joel E Kleinman, Davide Marnetto, Silvia Pellegrini, Antonio Rampino, Benedetto Vitiello, Stephan Ripke, Alice Braun, Julia Kraft, Sintia Iole Belangero, Paulo R Menezes, Celso Arango, James T R Walters, Michael C O'Donovan, Michael J Owen, David Braff, Aiden Corvin, Derek W Morris, Enrico Domenici, Jim van Os, Esref Atbaşoğlu, Meram C Saka, Marta Di Forti, Bernhard T Baune, Carlos N Pato, Andrew McQuillin, Vera Golimbet, Nikolay Kondratyev, Valentina Escott-Price, Anna Gareeva, Elza Khusnutdinova, Jorge A Cervilla, Margarita Rivera, Dominique Campion, Claudine Laurent-Levinson, Alessandro Serretti, Ole A Andreassen, David St Clair, Todd Lencz, Anil K Malhotra, Nina S McCarthy, Bryan J Mowry, Dan Rujescu, Ina Giegling, Annette M Hartmann, Bettina Konte, Markus M Nöthen, Marcella Rietschel, George Kirov, Patrick F Sullivan, Tracey L Petryshen, Thomas Werge, Andrew M McIntosh, Tõnu Esko, Erik G Jönsson, Hannelore Ehrenreich, Brien P Riley, Douglas F Levinson, Joseph D Buxbaum, Elvira Bramon, Christina M Hultman, Roel A Ophoff, Rolf Adolfsson, Eli A Stahl, Sinan Guloksuz, Bart P F Rutten, Cristina M Del-Ben, Florence Thibaut, Daniel R Weinberger, Giulio Pergola"
date: 2026-06-22
pdf: "https://pubmed.ncbi.nlm.nih.gov/42332269/"
tags: ["query:scz-model"]
score: 7.0
evidence: 通过反式eQTL建模在人脑组织中发现新的精神分裂症相关基因，与精神分裂症疾病模型研究相关
tldr: 复杂疾病相关的非编码遗传变异多通过调控基因表达影响风险，但现有转录组关联分析（TWAS）主要建模顺式（cis）效应，忽略了大量反式（trans）调控信息。作者利用六个脑区的RNA测序数据，开发了INGENE和MODULE两种模型，捕捉基因共表达网络中候选反式作用变异的综合影响，并与传统cis模型整合。该框架显著提升了18744个基因的表达预测准确性，在精神分裂症GWAS数据中鉴定出766个相关基因，其中641个为既往TWAS未报道的新基因，凸显了反式调控与基因网络在精神分裂症遗传风险中的重要作用。
source: pubmed
selection_source: fresh_fetch
motivation: 传统TWAS仅建模顺式遗传效应，难以解释基因表达调控中反式及网络层面的贡献。
method: 基于脑区共表达网络，构建INGENE和MODULE模型整合反式调控变异，并与cis模型联合预测基因表达。
result: 18744个基因表达预测得到改善，精神分裂症关联分析新发现641个此前未报道的风险基因。
conclusion: 整合共表达网络的反式调控信息可显著提升TWAS效能，揭示精神分裂症新的遗传机制。
---

## 摘要
大多数与复杂遗传性表型相关的遗传变异位于非编码区，被认为通过调控基因表达来影响疾病风险。然而，多数转录组关联分析方法主要建模局部（顺式）遗传效应，导致大量基因调控机制未被解释。在本研究中，我们证明纳入远端（反式）调控效应可改进基因表达预测及疾病相关基因的识别。利用来自六个人类死后脑区的RNA测序数据，我们开发了INGENE和MODULE两种模型，用于捕捉基因共表达网络内候选反式作用变异的综合影响。将这些模型与传统的顺式预测模型相结合，改善了18,744个基因在各脑区的基因表达填补（最大似然估计，α = 0.05）。将该框架应用于精神病基因组学联盟（Psychiatric Genomics Consortium）第三期基因型数据，鉴定出766个与精神分裂症相关的基因（PFDR < 0.01），其中641个此前未在转录组关联分析中报道。这些发现凸显了远端调控机制及基因网络相互作用对精神分裂症风险的贡献。

## Abstract
Most genetic variants associated with complex heritability phenotypes lie in non-coding regions and are thought to influence disease risk by regulating gene expression. However, most transcriptome-wide association approaches primarily model local (cis) genetic effects, leaving much of gene regulation unexplained. Here, we show that incorporating distal (trans) regulatory effects improves the prediction of gene expression and the identification of disease-associated genes. Using RNA sequencing data from six human post-mortem brain regions, we developed INGENE and MODULE, two models capturing the combined influence of candidate trans-acting variants within gene coexpression networks. Integrating these models with conventional cis-based predictors improved gene expression imputation (maximum likelihood estimation, α = 0.05) for 18,744 genes across regions. Applying this framework to Psychiatric Genomics Consortium wave 3 genotypes identified 766 genes associated with schizophrenia (PFDR < 0.01), including 641 not previously reported by transcriptome-wide analyses. These findings highlight the contribution of distal regulatory mechanisms and gene network interactions to schizophrenia risk.