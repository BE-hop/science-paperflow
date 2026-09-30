# Paperflow

Paperflow 是本地优先的多论文科研与 SCI 投稿工作流。它管理项目状态和可追溯资产，不自动投稿，也不把原始论文或期刊模板发送到外部服务。

完整的文件架构、数据字段、全部命令、状态/关卡、故障排查和两条端到端案例，请阅读：[Paperflow 用户说明书](../docs/USER_MANUAL.md)。

## Quick start

普通使用请返回 `science/` 目录，双击 `Start Paperflow.command`。浏览器工作台会把以下命令包装成建项向导、文件上传、下一步提示、人工关卡和 Agent 任务，用户不需要记忆 CLI。

网页中的职责边界：

- 用户：选择、审核、批准和最终投稿决定；
- 系统：创建目录、冻结文件、计算哈希、更新状态和执行检查；
- Agent：在隔离副本中生成候选翻译、研究/期刊/返修材料和风险报告；
- Agent 输出只有在用户点击“接受 Agent 结果”后才会应用到正式论文。

CLI 保留用于开发和排错，从 `science/` 目录运行：

```bash
python -m paperflow new \
  --title "中文论文标题" \
  --slug example-study \
  --entry existing_chinese

python -m paperflow freeze-source P-2026-001 /absolute/path/manuscript.docx
python -m paperflow extract-docx P-2026-001
python -m paperflow approve-gate P-2026-001 G0 --note "中文源稿范围已人工确认"
python -m paperflow set-status P-2026-001 translating
python -m paperflow rebuild
python -m paperflow check --all
```

使用 `--root` 或 `PAPERFLOW_ROOT` 可在临时目录或其他论文中心运行同一工具。

## Two entry paths

- `existing_chinese`：冻结中文源稿 → 建立段落映射和术语表 → 人工确认英文主稿 → 期刊转换。
- `new_research`：研究问题 → 文献与证据 → 实验/分析 → 英文主稿 → 期刊转换。

两条路径都必须从 `03_manuscript/master_en.docx` 派生期刊稿；禁止在上一家期刊的派生稿上换刊改造。

## Translation records

`02_translation/segments.jsonl` 每行一个内容单元：

```json
{"unit_id":"P001","kind":"paragraph","source_locator":"word/document.xml:p[1]","source_zh":"中文原文","candidate_en":"Draft translation","final_en":"Confirmed translation","status":"confirmed","change_reason":"","terminology_risks":[],"fact_risks":[]}
```

允许的状态为 `not_started`、`draft`、`review`、`confirmed`、`not_applicable`。标题、摘要、段落、表格单元格、图表标题、脚注和补充材料都应获得稳定 ID。

## Evidence and claims

`evidence/evidence.jsonl` 保存来源或实验证据，`evidence/claims.jsonl` 保存论文结论。核心结论必须列出可解析的 `evidence_ids`：

```json
{"evidence_id":"E001","type":"literature","locator":"doi:10.xxxx/example","version":"publisher-version","method":"direct reading","summary":"Evidence summary","uncertainty":"Scope limitation"}
{"claim_id":"C001","text":"Claim text","status":"inferred","core":true,"evidence_ids":["E001"],"limitations":"Known limitation"}
```

## Journal workflow

```bash
python -m paperflow journal-init P-2026-001 \
  --journal "Journal Name" \
  --article-type "Original Article" \
  --guidelines-url "https://official.example/author-guidelines" \
  --verified-at "2026-07-16" \
  --template /absolute/path/official-template.docx
```

该命令复制并哈希官方模板、创建 `journal.yaml` 和 `artifact.md`，但不会修改模板。正式转换必须遵循：

1. 使用 Documents Skill 的 `template-distill.md` 渲染和审计官方模板，完成 `artifact.md`。
2. 校验模板哈希，从模板创建工作副本并将英文主稿映射到明确槽位。
3. 用 `render_and_diff.py` 比较官方模板和派生稿，检查全部派生稿页面。
4. 运行 `paperflow docx-audit` 检查批注、修订、占位符和盲审元数据。
5. 记录结构审计、视觉检查人、时间和结论到该期刊的 `qa/`。

未知期刊要求必须保留为空或 `UNRESOLVED`，不得由 Agent 猜测。

结构审计和全页视觉检查完成后，分别记录证据：

```bash
python -m paperflow journal-qa P-2026-001 journal-slug structural_audit pass --evidence "04_journal/journal-slug/qa/structure.md"
python -m paperflow journal-qa P-2026-001 journal-slug render_review pass --reviewer "human-name" --evidence "04_journal/journal-slug/qa/render-review.md"
```

换刊时先把当前 profile 标记为 `superseded` 或 `withdrawn` 并说明原因，再创建新的 profile；旧模板和派生稿继续保留。

## Gates

- G0：研究问题或中文源稿范围。
- G1：翻译内容和术语。
- G2：目标期刊、稿件类型和官方要求。
- G3：科学内容、引用和版式。
- G4：投稿包、匿名和隐私。
- G5：审稿回复和返修提交。

`approve-gate` 只记录明确人工批准，并阻止跳过前置关卡。系统不会代替用户批准。

## Validation boundary

`paperflow check` 能检查元数据、哈希、映射覆盖、证据关系和部分 DOCX 结构。它不能证明翻译准确、科研结论正确或页面视觉合格；这些仍需人工审阅与 DOCX 全页渲染。
