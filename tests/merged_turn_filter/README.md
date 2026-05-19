# Merged Turn Filter

本目录原来保存 `merged.jsonl` 多轮电话切块、LLM 标注、query 拆分和导出中间产物。

这些中间产物已经归档到：

```text
archive/20260519_eval_chain_cleanup/data_intermediate/merged_turn_filter/
```

当前只保留 `chunk_summary.json`，因为 `tests/eval/merged_multi_turn_skill_recall.py` 会用它读取原始 merged 总样本数。

