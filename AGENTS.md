# 金融客服坐席话术推荐系统

## 项目结构

- 当前目录即项目根目录。
- `fin_copilot/` 是运行时代码，FastAPI 入口为 `fin_copilot/main.py`，主编排为 `fin_copilot/orchestrator.py`。
- `skills/` 是当前 Skill-based 业务定义层，`skills/registry.json` 与 `skills/definitions/*.yaml` 是 skill 事实来源。
- `sop/` 是保留的 SOP 业务知识资产，日常开发不要直接改原始 SOP 文件。
- `tests/eval/`、`scripts/`、`run_golden_model_matrix.sh` 是离线评测和数据处理入口。

## 当前开发入口

- 项目总览：`/Users/bytedance/Project/weixin/README.md`
- 当前评测链路、数据、报告策略：`/Users/bytedance/Project/weixin/docs/当前评测链路索引.md`
- 离线评测 Runbook：`/Users/bytedance/Project/weixin/tests/EVAL_RUNBOOK.md`
- 当前项目说明长文档：`/Users/bytedance/Project/weixin/docs/项目说明文档.md`

## 关键口径

- 当前主评测集是 `golden_test.jsonl`，不是旧的 `merged.jsonl` 或 `test.jsonl`。
- 多轮电话主评测入口是 `tests/eval/merged_multi_turn_skill_recall.py`，常用模型 profile 是 `deepseek-v4-flash`。
- 旧单 query 评测入口 `scripts/run_golden_full_eval.sh` 仍保留，用于 `raw_test.jsonl` 的 Exp1/Exp2/Exp3。
- `tests/reports/*` 是本地运行产物，默认被 `.gitignore` 忽略；交付给别人时应以脚本、tracked 数据和文档作为可复现入口。
