# checkht
## 抽取的原文定位（借鉴 google/langextract）

`step1` / `step2` 的抽取现在带 `evidence`（逐字摘自原文），由 `grounding.py` 在原文里定位并核对：

- `output/bid_result.json`、`output/contract_result.json`：格式不变（`{"字段": {"value": ...}}`），step3 不用改。
- `output/*_result.grounded.json`：每个字段的 evidence、原文字符位置、状态（`verified` / `partial` / `unverified` / `no_evidence` / `empty`）和警告（value 里的数字在原文找不到时提示）。
- 状态为 `unverified` / `no_evidence` 的字段会自动补抽一轮；仍不过的保留并标记，不会静默丢弃，需要人工核对。
- 原文超过 `CHECKHT_CHUNK_CHARS`（默认 80000 字符）时自动分块、块间重叠 `CHECKHT_CHUNK_OVERLAP`（默认 2000）、逐块抽取后合并。`CHECKHT_EXTRA_PASSES=0` 可关闭补抽。
- 测试：`python -m unittest tests.test_grounding`
