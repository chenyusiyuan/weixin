# Scripts Index

脚本按用途理解，不按物理目录继续拆分，避免破坏已有命令路径。

## 当前评测

| 脚本 | 用途 |
|---|---|
| `run_golden_full_eval.sh` | 旧单 query `raw_test.jsonl` 的 Exp1/Exp2/Exp3 总入口 |
| `tests/eval/merged_multi_turn_skill_recall.py` | 当前多轮电话 call 级 TopK 评测 |
| `run_multiturn_model_profiles.sh` | Flash/Pro 多轮评测命令矩阵，默认直接按映射表计分、不跑 LLM audit |
| `eval_real_multiturn_branch_selection.py` | 多轮场景下 branch 选择诊断 |
| `eval_real_query_branch_selection.py` | 单 query 场景下 branch 选择诊断 |
| `eval_tool_flow_branch_selection.py` | mock tool flow 场景下 branch 选择诊断 |

## 数据构建

| 脚本 | 用途 |
|---|---|
| `prepare_merged_turn_labeling_chunks.py` | 从 `merged.jsonl` 切多轮电话标注 chunk |
| `merge_merged_turn_labels.py` | 合并 chunk 标签，生成可测 query |
| `export_raw_scorable_queries.py` | 导出原话客户 query |
| `apply_raw_query_split_decisions.py` | 应用 query 拆分决策 |
| `export_merged_raw_eval_dataset.py` | 导出当前 `golden_test.jsonl` |
| `export_golden_test.py` | 导出旧单 query 测试集 |
| `rebuild_golden_from_batches.py` | 从历史 batch 标注重建 `raw_test.jsonl` |

## 审计与辅助

| 脚本 | 用途 |
|---|---|
| `analyze_merged_error_skill_alignment.py` | 多轮错例与 skill 对齐分析 |
| `audit_sop_skill_coverage.py` | SOP 与 skill 覆盖审计 |
| `propose_route_a_rules.py` | 从旧单 query 数据中建议 Chain A 规则 |
| `refine_route_a_rule.py` | 调整 Chain A 规则 |
| `validate_skills.py` | 校验 Skill registry 和 YAML |
| `build_value_added_text_blocks.py` | 构建增值服务文本知识块 |
| `build_value_added_image_blocks.py` | 构建增值服务图片知识块 |
