# 20260519 评测链路归档

本目录保存本次整理时从项目工作区移出的历史文档、旧实验报告、打标中间产物、缓存和运行日志。

归档原则：

- 保留当前可运行入口在原位置，不移动生产代码、Skill、SOP、正式测试集和当前映射表。
- 历史报告、一次性分析文档、打标切分产物、旧 batch 标注结果、缓存和日志统一收敛到本目录。
- 所有移动记录见 `manifest.json`。

## 目录

| 目录 | 内容 |
|---|---|
| `docs_history/` | 历史设计文档、旧评测说明、旧分支实验文档、旧覆盖率审计、图片资产 |
| `reports_history/` | `tests/reports/` 中除当前两份保留报告外的历史实验输出 |
| `data_intermediate/` | 旧单 query pipeline 中间产物、多轮打标切分产物、sub-agent batch 验证产物 |
| `caches/` | embedding / skill cosine / query embedding 缓存 |
| `logs/` | 历史运行日志 |
| `root_history/` | 根目录历史重复文档 |

## 当前仍保留在工作区的关键入口

| 类型 | 路径 |
|---|---|
| 当前多轮 golden | `golden_test.jsonl` |
| 旧单 query 测试集 | `raw_test.jsonl` |
| 原始 merged 电话数据 | `merged.jsonl` |
| 旧单 query 原始数据 | `raw_data.csv` |
| 标注维度 | `标注维度.xlsx` |
| 小结到 SOP/skill 映射 | `scripts/references/merged_intent_skill_mapping.json` |
| 当前多轮路由结果 | `tests/reports/merged_multi_turn_after_corporate_repay_tuning_20260427/` |
| 当前映射重算结果 | `tests/reports/merged_mapping_recalc_from_previous_20260519/` |
| 当前链路索引 | `docs/当前评测链路与归档索引.md` |

