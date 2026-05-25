# Merged Turn Filter

本目录原来保存多轮电话切块、LLM 标注、query 拆分和导出中间产物；旧文档里常称源文件为 `merged.jsonl`，当前仓库中的源文件名是 `原始300条数据.jsonl`。

历史中间产物不随交付保留。当前只保留 `chunk_summary.json`，因为 `tests/eval/merged_multi_turn_skill_recall.py` 会用它读取全量多轮原始样本分母。该 JSON 不再代表可用 chunk 文件列表。
