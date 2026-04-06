# TouchDesigner KB Bundle

这个技能已经把运行所需的知识库数据内置在技能目录中，不依赖项目根目录下的 `touchdesigner_kb` 或 `touchdesigner_docs`。

## 目录结构

- `touchdesigner_kb/stats.json`
	- 知识库规模统计
- `touchdesigner_kb/family_compatibility.jsonl`
	- OP 家族级版本兼容索引
- `touchdesigner_kb/version_compatibility.jsonl`
	- 实体级版本兼容索引
- `touchdesigner_kb/chunks.jsonl`
	- 切块后的检索语料
- `touchdesigner_kb/documents.jsonl`
	- 完整文档语料
- `touchdesigner_kb/assets_high_value.jsonl`
	- 高价值附件索引

## 推荐使用顺序

1. 先查 `family_compatibility.jsonl`
2. 再查 `version_compatibility.jsonl`
3. 然后查 `chunks.jsonl`
4. 必要时再查 `documents.jsonl`
5. 若需要示例资源，再查 `assets_high_value.jsonl`

## 推荐查询方式

优先使用技能内脚本：

```bash
python3 scripts/query_kb.py families POP
python3 scripts/query_kb.py entities "feedback pop" --target-version 2023.11600
python3 scripts/query_kb.py chunks "add top"
python3 scripts/query_kb.py documents "particle system"
```

如果脚本结果不足，再直接读取对应 JSONL 文件。
