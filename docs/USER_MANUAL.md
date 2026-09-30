# Paperflow 用户说明书

> 适用版本：Paperflow `0.2.0`  
> 工作目录：`/Users/mac/Documents/LIFE/career/science`  
> 本手册面向论文作者。命令、字段名和状态值使用英文，解释使用中文。

## 目录

0. [本地网页工作台](#0-本地网页工作台)
1. [系统概览](#1-系统概览)
2. [安装与运行](#2-安装与运行)
3. [文件架构](#3-文件架构)
4. [核心数据文件](#4-核心数据文件)
5. [状态、轨道和人工关卡](#5-状态轨道和人工关卡)
6. [完整命令参考](#6-完整命令参考)
7. [多论文并行管理](#7-多论文并行管理)
8. [期刊模板和 DOCX 流程](#8-期刊模板和-docx-流程)
9. [检查器与故障排查](#9-检查器与故障排查)
10. [案例 A：中文旧稿翻译并投稿](#10-案例-a中文旧稿翻译并投稿)
11. [案例 B：从研究问题开始写新论文](#11-案例-b从研究问题开始写新论文)
12. [日常使用清单](#12-日常使用清单)

---

## 0. 本地网页工作台

Paperflow `0.2.0` 的默认入口是本地浏览器工作台。普通用户不需要记忆命令。

在 Finder 中打开：

```text
/Users/mac/Documents/LIFE/career/science
```

双击 `Start Paperflow.command`。系统会启动仅绑定 `127.0.0.1` 的本地服务并自动打开浏览器。关闭启动器所在的终端窗口即可停止服务。

### 0.1 用户只需要做什么

- 新建论文时选择“已有中文稿”或“从研究问题开始”；
- 上传原稿、英文主稿、官方期刊模板和投稿文件；
- 审核 Agent 生成的候选译文、文稿、期刊材料和风险报告；
- 明确批准 G0–G5；
- 决定是否接受 Agent 输出、是否推进状态以及是否实际投稿。

首页每篇论文只有一个主要按钮“继续下一步”。单篇论文页面将原有命令归并为五个阶段：建立项目、准备论文内容、选择目标期刊、准备投稿、审稿与返修。

### 0.2 系统自动做什么

系统直接调用 Paperflow Python 服务完成建目录、冻结文件、哈希、DOCX 内容提取、状态更新、组合看板和检查，不会把网页输入拼接成 Shell 命令。

### 0.3 Agent 如何工作

点击“交给 Agent”后，网页调用当前机器已经登录的 Codex CLI，不需要配置 OpenAI API Key，但仍需要有效的 ChatGPT 登录和网络。Agent 在：

```text
papers/.paperflow/jobs/<job-id>/workspace/
```

中的临时论文副本工作。正式论文不会随 Agent 运行而变化。Agent 完成后，网页展示摘要、问题、候选文件和检查记录；只有用户点击“接受 Agent 结果”，受控应用器才会检查允许路径、并发冲突和文件格式，然后更新正式论文并重建看板。

Agent 不得修改 `PAPER.yaml`、冻结原稿、官方模板或投稿回执，不得批准 G0–G5，不得宣布科研结论、翻译或版式已经人工确认。

### 0.4 Agent 不可用时

如果 Codex 未安装、未登录或网络不可用，网页会显示“Agent 暂不可用”。建项、上传、提取、人工关卡、状态推进、文件查看和项目检查仍然可用。

### 0.5 开发与排错入口

网页内部入口为：

```bash
python3 -m paperflow web
python3 -m paperflow web --port 8770
python3 -m paperflow web --no-browser
```

`web` 只允许本机访问；`--no-browser` 用于测试或已有浏览器窗口的场景。

---

## 1. 系统概览

Paperflow 是一个本地优先的多论文项目管理工具。它把每篇论文放在独立目录中，记录原稿、调研、翻译、英文主稿、目标期刊、投稿材料、审稿意见和项目状态。

它主要解决以下问题：

- 同时推进多篇论文时，知道每篇论文进行到哪里、下一步是什么；
- 中文原稿翻译成英文时，能够逐段追踪，避免漏译和静默改变科学含义；
- 更换期刊时，保留旧期刊版本，并从英文权威主稿重新派生；
- 投稿前检查引用、证据、批注、修订痕迹、占位符和部分匿名信息；
- 避免覆盖中文原稿、官方模板和历史投稿材料。

Paperflow **不会**：

- 自动判断翻译是否准确；
- 自动证明科研结论正确；
- 自动确认期刊官网要求仍然最新；
- 自动完成 Word 全页视觉验版；
- 自动投稿或代表用户批准 G0–G5；
- 自动删除、覆盖原稿或旧投稿版本。

### 1.1 四层结构

```text
论文组合 papers/
└── 独立论文项目 P-YYYY-NNN-short-title/
    ├── 五条工作轨道 tracks
    ├── 一个总体状态 overall_status
    └── 六个人工关卡 G0-G5
```

- **论文组合**：保存所有论文的索引和状态看板。
- **独立论文项目**：每篇论文有自己的目录、文件和状态，不共享可变稿件。
- **工作轨道**：研究、稿件、翻译、期刊、投稿可以并行推进。
- **人工关卡**：关键阶段必须由人确认，Agent 只能准备材料和报告问题。

### 1.2 哪些文件是事实源

每篇论文的 `PAPER.yaml` 是项目状态的权威来源。

组合根目录中的：

- `INDEX.yaml`：机器可读索引；
- `STATUS.md`：人可以阅读的状态表；

都是由所有 `PAPER.yaml` 重建的派生文件。不要手工编辑这两个文件；运行 `rebuild` 即可重新生成。

---

## 2. 安装与运行

### 2.1 要求

- Python 3.11 或更高版本；
- PyYAML 6.0 或更高版本；
- 处理真实 DOCX 视觉版式时，还需要 Codex Documents Skill 所使用的文档运行环境。

从项目根目录运行：

```bash
cd /Users/mac/Documents/LIFE/career/science
python3 -m paperflow --help
```

如果当前 Python 环境缺少项目依赖，可在你自己的虚拟环境中安装：

```bash
python3 -m pip install -e .
```

### 2.2 查看帮助

查看全部命令：

```bash
python3 -m paperflow --help
```

查看某个命令的参数：

```bash
python3 -m paperflow new --help
python3 -m paperflow journal-init --help
python3 -m paperflow check --help
```

### 2.3 论文中心路径

默认论文中心是当前目录下的 `papers/`。因此应先进入 `science/` 再运行命令。

临时指定另一个论文中心时，`--root` 必须写在子命令之前：

```bash
python3 -m paperflow --root /absolute/path/to/papers new \
  --title "Example" --slug example --entry new_research
```

也可以设置环境变量：

```bash
export PAPERFLOW_ROOT=/absolute/path/to/papers
python3 -m paperflow rebuild
```

优先级为：命令行 `--root` → `PAPERFLOW_ROOT` → 当前目录下的 `papers/`。

---

## 3. 文件架构

### 3.1 论文组合

```text
papers/
├── AGENTS.md
├── README.md
├── INDEX.yaml                 # 自动生成
├── STATUS.md                  # 自动生成
├── shared/                    # 经审核的跨论文稳定资源
├── templates/                 # 数据格式参考模板
├── P-2026-001-first-paper/
└── P-2026-002-second-paper/
```

### 3.2 单篇论文

```text
P-2026-001-short-title/
├── PAPER.yaml                 # 状态事实源
├── README.md
├── 00_source/                 # 冻结的中文原稿和原始附件
├── 01_research/
│   ├── research-question.md   # 新研究路径的 G0 输入
│   ├── literature/
│   └── experiments/
├── 02_translation/
│   ├── segments.jsonl         # 段落级中英映射
│   ├── glossary.yaml          # 术语表
│   └── batches/
├── 03_manuscript/
│   └── master_en.docx         # 英文权威主稿
├── 04_journal/
│   └── journal-slug/
│       ├── journal.yaml       # 期刊要求和 QA 状态
│       ├── artifact.md        # 从官方模板提取的版式契约
│       ├── official/          # 官方模板，不可覆盖
│       ├── derived/           # 该期刊的派生稿
│       └── qa/                # 结构和渲染检查证据
├── 05_submission/             # 最终投稿包
├── 06_reviews/                # 编辑信、审稿意见和返修轮次
├── references/
│   ├── library.bib
│   └── citations.jsonl
├── evidence/
│   ├── evidence.jsonl
│   └── claims.jsonl
├── decisions/                 # 换刊等关键决策
└── qa/                        # 论文级检查报告
```

### 3.3 各区域的编辑规则

| 路径 | 内容 | 权威性 | 谁修改 | 能否重建 | 覆盖规则 |
| --- | --- | --- | --- | --- | --- |
| `PAPER.yaml` | 状态、关卡、轨道、源稿和期刊索引 | 权威 | CLI；任务和阻塞项可人工维护 | 否 | 不要用旧副本覆盖 |
| `00_source/` | 冻结原稿 | 权威输入 | 只通过 `freeze-source` 新增 | 否 | 禁止覆盖或原地编辑 |
| `02_translation/` | 翻译单元与术语 | 权威过程记录 | 人或 Agent 审校 | 可从原稿重新提取空白映射，但不能覆盖已翻译记录 | 禁止无备份重建 |
| `03_manuscript/master_en.docx` | 英文权威主稿 | 权威稿件 | 人或文档 Agent | 否 | 使用版本化修改流程 |
| `04_journal/*/official/` | 官方模板 | 权威输入 | 只通过 `journal-init` 新增 | 否 | 禁止覆盖或编辑 |
| `04_journal/*/derived/` | 期刊派生稿 | 派生稿 | 文档 Agent/人工 | 可从主稿和模板重建 | 不作为换刊起点 |
| `05_submission/` | 实际投稿文件 | 交付记录 | 人工最终确认 | 否 | 历史投稿包不得覆盖 |
| `06_reviews/` | 审稿与返修记录 | 历史证据 | 人工/Agent | 否 | 按轮次新增 |
| `INDEX.yaml`、`STATUS.md` | 组合索引和看板 | 派生 | `rebuild` | 是 | 不手工编辑 |

### 3.4 三种英文稿件的区别

- `03_manuscript/master_en.docx`：内容权威版本，不绑定某一家期刊格式。
- `04_journal/<journal>/derived/manuscript.docx`：从英文主稿套用某期刊模板得到的派生稿。
- `05_submission/*.docx`：经过匿名、清洁、命名和投稿包检查后实际准备提交的文件。

换刊时，应从 `master_en.docx` 为新期刊重新派生，不能在旧期刊派生稿上继续改格式。

---

## 4. 核心数据文件

模板可参考 [`papers/templates/`](../papers/templates/)。

### 4.1 `PAPER.yaml`

创建论文时自动生成。最小结构参考 [`PAPER.yaml` 模板](../papers/templates/PAPER.yaml)。

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| `paper_id` | 稳定论文 ID | `P-2026-001` |
| `title` | 完整标题 | `城市热环境研究` |
| `short_title` | 目录短名来源 | `urban-heat` |
| `entry_path` | 入口路径 | `existing_chinese` / `new_research` |
| `overall_status` | 总体阶段 | `translating` |
| `tracks` | 五个并行工作轨道 | 见第 5.2 节 |
| `current_tasks` | 当前任务列表 | `['确认术语']` |
| `blockers` | 阻塞项列表 | `['等待数据授权']` |
| `next_gate` | 下一个人工关卡 | `G1` |
| `target_date` | 目标日期 | `2026-10-01` |
| `gates` | G0–G5 批准记录 | `approved/approved_at/note` |
| `source_files` | 冻结源稿路径和哈希 | 由 `freeze-source` 生成 |
| `journal_profiles` | 期刊 profile 索引 | 由 `journal-init` 生成 |

不要手工修改 `paper_id`、源稿哈希或已经批准的关卡。若需纠正历史，应记录新决策，而不是抹去旧记录。

### 4.2 `segments.jsonl`

JSONL 表示“一行一个完整 JSON 对象”，不是一个带方括号的 JSON 数组。

```json
{"unit_id":"U000001","kind":"paragraph","source_part":"word/document.xml","source_locator":"word/document.xml:document/body[1]/p[1]","source_sha256":"...","source_zh":"本研究分析……","candidate_en":"This study analyzes...","final_en":"This study investigates...","status":"confirmed","change_reason":"Improve academic precision","terminology_risks":[],"fact_risks":[]}
```

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 稳定且唯一的翻译单元 ID |
| `kind` | `title`、`subtitle`、`paragraph`、`table_cell`、`caption`、`header`、`footer`、`footnote` 或 `endnote` |
| `source_locator` | 原 DOCX 中的结构定位 |
| `source_sha256` | 该单元来自哪一个冻结源稿 |
| `source_zh` | 中文原文，不能静默改写 |
| `candidate_en` | 翻译草稿 |
| `final_en` | 人工确认后的英文 |
| `status` | `not_started`、`draft`、`review`、`confirmed`、`not_applicable` |
| `change_reason` | 语言或内容调整理由 |
| `terminology_risks` | 术语风险列表 |
| `fact_risks` | 数值、因果、确定性等事实风险列表 |

常见错误：重复 `unit_id`、删除中文源文、把 `status` 设为 `confirmed` 但没有 `final_en`、把整个文件改成 JSON 数组。

### 4.3 `glossary.yaml`

参考 [`glossary.yaml` 模板](../papers/templates/glossary.yaml)：

```yaml
schema_version: '1.0'
terms:
  - source_zh: 热岛效应
    preferred_en: urban heat island effect
    forbidden_en: [heat island phenomenon]
    abbreviation: UHI
    source: domain convention
    note: Use the abbreviation only after first definition.
```

每个 `source_zh` 只能出现一次，并且必须有 `preferred_en`。`forbidden_en` 用于记录容易出现但不希望使用的译法。

### 4.4 `evidence.jsonl` 与 `claims.jsonl`

证据示例：

```json
{"evidence_id":"E001","type":"literature","locator":"doi:10.1234/example","version":"publisher-version","method":"direct reading","summary":"The study reports...","uncertainty":"Single-city sample"}
```

结论示例：

```json
{"claim_id":"C001","text":"The intervention reduced the primary outcome.","status":"inferred","core":true,"evidence_ids":["E001"],"limitations":"Observational evidence only"}
```

- `core: true` 的核心结论必须至少关联一个证据 ID。
- `evidence_ids` 中的每个 ID 必须存在于 `evidence.jsonl`。
- `status` 应区分假设、直接观察和推断，不要把推断写成已证实事实。

### 4.5 `library.bib` 与 `citations.jsonl`

`library.bib` 保存 Zotero/BibTeX 条目：

```bibtex
@article{wang2026urban,
  title = {Example title},
  author = {Wang, Example},
  year = {2026}
}
```

`citations.jsonl` 保存正文中的引用位置：

```json
{"citation_id":"R001","citekey":"wang2026urban","locator":"03_manuscript/master_en.docx:Introduction"}
```

`citekey` 必须在 `library.bib` 中存在，BibTeX key 不能重复。

### 4.6 `journal.yaml`

参考 [`journal.yaml` 模板](../papers/templates/journal.yaml)。重要字段包括：

- `status`：`active`、`superseded` 或 `withdrawn`；
- `official_guidelines_url` 和 `requirements_verified_at`：官方来源及核验日期；
- `official_template`：模板路径、哈希和大小；
- `limits`、`section_order`、`reference_style`：期刊要求；
- `blind_review`：是否需要匿名稿；
- `required_submission_files`：G4 必须存在的投稿文件；
- `master_manuscript` 和 `derived_manuscript`：内容源与派生稿路径；
- `qa.structural_audit` 和 `qa.render_review`：G3 使用的 QA 记录。

未知期刊要求使用空值或 `UNRESOLVED`，不要猜测。

### 4.7 QA 记录

QA 证据文件建议放在 `04_journal/<journal>/qa/`，例如：

```text
structure.md
render-review.md
template-diff/
```

`journal-qa` 命令只把检查结果登记到 `journal.yaml`；它本身不会执行 Word 渲染，也不会自动判断页面合格。

---

## 5. 状态、轨道和人工关卡

### 5.1 总体状态迁移

当前 `0.2.0` 数据模型实际包含 15 个总体状态。原始建设计划中的“16 个”是计数笔误；本手册以下表和当前代码为准。`set-status` 只允许以下迁移：

| 当前状态 | 允许的下一状态 |
| --- | --- |
| `idea` | `exploring`、`drafting`、`parked` |
| `exploring` | `drafting`、`parked` |
| `drafting` | `translating`、`journal_targeting`、`internal_review`、`parked` |
| `translating` | `language_review`、`parked` |
| `language_review` | `translating`、`journal_targeting`、`parked` |
| `journal_targeting` | `formatting`、`parked` |
| `formatting` | `internal_review`、`journal_targeting`、`parked` |
| `internal_review` | `drafting`、`translating`、`formatting`、`ready_to_submit`、`parked` |
| `ready_to_submit` | `internal_review`、`submitted`、`parked` |
| `submitted` | `under_review`、`revision`、`accepted`、`rejected` |
| `under_review` | `revision`、`accepted`、`rejected` |
| `revision` | `internal_review`、`ready_to_submit`、`submitted`、`accepted`、`rejected` |
| `accepted` | 无；终态 |
| `rejected` | `journal_targeting`、`parked` |
| `parked` | `idea`、`exploring`、`drafting`、`journal_targeting` |

重复设置为当前状态是允许的。跳过状态会返回 `Illegal status transition`。

### 5.2 五个工作轨道

| 字段 | 含义 |
| --- | --- |
| `research_status` | 调研、研究问题、实验和分析 |
| `manuscript_status` | 主稿写作与内部审阅 |
| `translation_status` | 中文到英文映射、翻译和确认 |
| `journal_status` | 选刊、要求核验和模板转换 |
| `submission_status` | 投稿包、提交、审稿和返修 |

每条轨道可使用：`not_started`、`in_progress`、`blocked`、`complete`、`not_applicable`。

总体状态回答“论文主要在哪个阶段”；轨道状态回答“每条并行工作线进展如何”。它们不会自动互相推导，需要按真实进展分别更新。

### 5.3 G0–G5

| 关卡 | 前置关卡 | 实际准入条件 |
| --- | --- | --- |
| G0 | 无 | `existing_chinese` 已登记至少一个冻结源稿；`new_research` 已填写非空 `01_research/research-question.md` |
| G1 | G0 | `03_manuscript/master_en.docx` 存在；中文旧稿还要求翻译单元全部为 `confirmed` 或 `not_applicable`，且确认项有 `final_en` |
| G2 | G0 | 至少建立一个期刊 profile；建议在 G1 后批准 |
| G3 | G0、G1、G2 | 英文主稿存在；恰好一个 `active` 期刊；派生稿存在；结构 QA 与人工全页渲染 QA 均登记为通过 |
| G4 | G0、G1、G2、G3 | `05_submission/` 至少一个 DOCX；活动期刊列出的必需文件存在；DOCX 结构检查无错误 |
| G5 | G4 | `06_reviews/` 至少有一个审稿轮次目录 |

批准示例：

```bash
python3 -m paperflow approve-gate P-2026-001 G0 \
  --note "中文源稿范围和附件已人工确认"
```

批准记录会保存批准时间和说明。不要让 Agent 自行填写虚假的人工批准。

---

## 6. 完整命令参考

所有示例默认先执行：

```bash
cd /Users/mac/Documents/LIFE/career/science
```

### 6.1 `new`

**用途**：创建独立论文项目并自动分配 ID。

```bash
python3 -m paperflow new \
  --title "城市热环境的多尺度分析" \
  --slug urban-heat \
  --entry existing_chinese \
  --year 2026
```

- `--slug` 必须至少包含一个 ASCII 字母或数字；建议使用短英文和连字符。
- `--entry` 只能是 `existing_chinese` 或 `new_research`。
- 同一年按现有项目自动分配 `001`、`002` 等编号。
- 修改：创建整套论文目录、`PAPER.yaml`、空翻译/证据/引用文件，并重建组合看板。
- 成功输出：新论文目录的绝对路径。
- 常见错误：slug 全为中文；目标目录已存在。修复 slug 或使用另一个短名，不要覆盖目录。

### 6.2 `freeze-source`

**用途**：把源稿复制进 `00_source/`，记录 SHA-256 和大小。

```bash
python3 -m paperflow freeze-source \
  P-2026-001 /absolute/path/chinese-manuscript.docx
```

- 前置：论文已创建，输入文件存在。
- 修改：新增冻结副本并更新 `PAPER.yaml.source_files`。
- 成功输出：冻结副本路径。
- 已有同名文件时命令拒绝覆盖。需要保存新版时，先给新版使用不同文件名，例如 `manuscript-v2.docx`。
- 后续 `check` 会重新计算哈希；不要在 `00_source/` 内编辑文件。

### 6.3 `extract-docx`

**用途**：从一个冻结 DOCX 提取正文、表格单元格、标题、页眉页脚和脚注等翻译单元。

```bash
python3 -m paperflow extract-docx P-2026-001
```

若登记了多个源稿：

```bash
python3 -m paperflow extract-docx P-2026-001 \
  --source-name chinese-manuscript.docx
```

- 前置：选中的文件是有效 DOCX，且哈希未变化。
- 修改：写入 `02_translation/segments.jsonl`，把翻译轨道设为 `in_progress`。
- 成功输出：`Extracted N translation unit(s)`。
- 为保护已有翻译，若 `segments.jsonl` 非空，命令拒绝覆盖。
- 当前提取基于 OOXML 文本节点；复杂文本框、公式内部文本或嵌入对象仍需人工核对。

### 6.4 `journal-init`

**用途**：建立目标期刊 profile，并复制、哈希官方模板。

```bash
python3 -m paperflow journal-init P-2026-001 \
  --journal "Example Journal" \
  --article-type "Original Article" \
  --guidelines-url "https://journal.example/author-guidelines" \
  --verified-at "2026-07-16" \
  --template /absolute/path/official-template.docx
```

- 前置：要求来自期刊官方来源；若已有活动期刊，先用 `journal-status` 处理旧 profile。
- 修改：创建 `04_journal/example-journal/`、`journal.yaml`、`artifact.md` 和官方模板副本；更新期刊轨道。
- 成功输出：期刊 profile 目录。
- `--template` 可省略，但之后必须补充真实官方模板和哈希，才能完成严谨模板转换。
- 同一 journal slug 已存在时拒绝覆盖。

### 6.5 `journal-status`

**用途**：激活、替代或撤回期刊目标，并记录换刊决策。

```bash
python3 -m paperflow journal-status \
  P-2026-001 example-journal superseded \
  --note "Desk rejection; prepare a new target from master_en.docx"
```

允许状态：`active`、`superseded`、`withdrawn`。

- 修改：更新该 `journal.yaml`，并向 `decisions/journal-changes.jsonl` 追加记录。
- 同一论文不允许同时存在两个活动期刊。
- 旧 profile 不会被删除；新期刊必须从英文主稿重新派生。

### 6.6 `journal-qa`

**用途**：登记已经实际完成的结构或全页视觉检查结果。

```bash
python3 -m paperflow journal-qa \
  P-2026-001 example-journal structural_audit pass \
  --evidence "04_journal/example-journal/qa/structure.md"

python3 -m paperflow journal-qa \
  P-2026-001 example-journal render_review pass \
  --reviewer "Researcher Name" \
  --evidence "04_journal/example-journal/qa/render-review.md"
```

- 检查类型：`structural_audit` 或 `render_review`。
- 结果：`pass` 或 `fail`。
- `render_review pass` 必须填写 `--reviewer`。
- 修改：只更新 `journal.yaml.qa`；不执行检查、不创建证据文件。
- 只有在真实检查完成后才能登记 `pass`。

### 6.7 `set-status`

**用途**：更新论文总体状态，并校验是否允许迁移。

```bash
python3 -m paperflow set-status P-2026-001 translating
```

- 修改：`PAPER.yaml.overall_status`、更新时间和组合看板。
- 成功时通常没有输出。
- 出现 `Illegal status transition` 时，查看第 5.1 节，先进入合法中间状态；不要手工绕过状态机。

### 6.8 `set-track`

**用途**：更新一个并行工作轨道。

```bash
python3 -m paperflow set-track \
  P-2026-001 translation_status complete
```

轨道字段：`research_status`、`manuscript_status`、`translation_status`、`journal_status`、`submission_status`。

- 修改：对应 `PAPER.yaml.tracks` 字段及组合看板。
- 轨道状态不自动批准关卡，也不自动改变总体状态。

### 6.9 `approve-gate`

**用途**：记录明确人工批准，并检查前置关卡和文件条件。

```bash
python3 -m paperflow approve-gate \
  P-2026-001 G1 \
  --note "全部翻译单元和术语已逐项人工核对"
```

- 修改：`PAPER.yaml.gates`、`next_gate`、更新时间和看板。
- 若不满足条件，返回 `Gx readiness failed` 并列出缺失项。
- `--note` 应说明谁确认了什么，而不是写“完成”。

### 6.10 `rebuild`

**用途**：扫描所有 `P-YYYY-NNN-*` 项目，从 `PAPER.yaml` 重建索引和看板。

```bash
python3 -m paperflow rebuild
```

- 修改：`papers/INDEX.yaml` 和 `papers/STATUS.md`。
- 成功输出：`Rebuilt portfolio with N paper(s)`。
- 不修改任何论文正文、翻译、证据或期刊文件。

### 6.11 `check`

检查单篇：

```bash
python3 -m paperflow check --paper P-2026-001
```

检查全部：

```bash
python3 -m paperflow check --all
```

- 成功输出：`PASS: no issues found`。
- 发现错误时输出 `ERROR [code] message`，并以非零退出码结束。
- 非零退出码表示检查未通过，不等于 Paperflow 崩溃。
- 检查范围见第 9 节；它不能证明翻译准确或页面视觉正确。

### 6.12 `docx-audit`

**用途**：独立检查一个 DOCX 包中的批注、修订、占位符和部分身份元数据。

```bash
python3 -m paperflow docx-audit \
  /absolute/path/submission.docx

python3 -m paperflow docx-audit \
  /absolute/path/blind-manuscript.docx \
  --blind-review
```

- 不修改 DOCX。
- `--blind-review` 额外检查创建者和最后修改者元数据。
- 结构检查通过不代表字体、分页、表格和图片布局正常；仍必须全页渲染检查。

---

## 7. 多论文并行管理

连续创建两篇论文：

```bash
python3 -m paperflow new \
  --title "Existing Chinese Study" \
  --slug existing-study \
  --entry existing_chinese \
  --year 2026

python3 -m paperflow new \
  --title "New Research Question" \
  --slug new-question \
  --entry new_research \
  --year 2026
```

预期目录：

```text
P-2026-001-existing-study/
P-2026-002-new-question/
```

分别更新：

```bash
python3 -m paperflow set-status P-2026-001 translating
python3 -m paperflow set-status P-2026-002 exploring
python3 -m paperflow set-track P-2026-001 translation_status in_progress
python3 -m paperflow set-track P-2026-002 research_status in_progress
python3 -m paperflow rebuild
```

打开 [`papers/STATUS.md`](../papers/STATUS.md) 可查看每篇论文的总体状态、五条轨道、下一关卡和更新时间。`current_tasks` 和 `blockers` 当前需要在各论文 `PAPER.yaml` 中谨慎维护，然后运行 `rebuild`。

### 每周维护建议

1. 运行 `python3 -m paperflow check --all`；
2. 打开 `papers/STATUS.md`；
3. 对照真实进展更新各论文的 `current_tasks` 和 `blockers`；
4. 用 `set-track` 更新并行轨道；
5. 只在主要阶段变化时使用 `set-status`；
6. 准备关卡材料，但由你决定是否执行 `approve-gate`；
7. 再次运行 `rebuild`。

---

## 8. 期刊模板和 DOCX 流程

### 8.1 正确顺序

1. 从期刊官网核验 Author Guidelines、文章类型和官方模板；
2. 用 `journal-init` 冻结官方模板和核验日期；
3. 渲染官方模板全部页面并运行结构审计；
4. 完成 `artifact.md` 中的页面、字体、样式、编号、表格、页眉页脚、槽位和保留部件；
5. 校验模板哈希，从官方模板创建工作副本；
6. 把 `master_en.docx` 内容映射到明确槽位；
7. 输出到 `derived/manuscript.docx`；
8. 执行结构审计、模板/成稿渲染差异和所有页面人工检查；
9. 把真实 QA 证据保存在 `qa/`；
10. 用 `journal-qa` 登记结果；
11. 满足其他条件后批准 G3。

### 8.2 三种检查的区别

| 检查 | 能发现 | 不能保证 |
| --- | --- | --- |
| `docx-audit` / OOXML 结构审计 | 批注、修订、占位符、部分元数据、关系和字段问题 | 页面是否好看、表格是否截断 |
| 模板与成稿像素差异 | 模板外的意外移动、页面结构变化 | 差异是否在科学内容上正确 |
| 全页人工视觉检查 | 字体、分页、截断、重叠、表格、图片、页眉页脚 | 隐藏 OOXML 关系或未渲染批注是否完整 |

三者互补，不能相互替代。

### 8.3 可以直接交给 Codex 的任务示例

模板提取：

> 请以 `04_journal/example-journal/official/template.docx` 为不可变模板，按照 Documents Skill 的 template-distill 流程渲染全部页面、审计结构，并完成同目录的 `artifact.md`。不要修改官方模板。

期刊派生稿：

> 请从 `03_manuscript/master_en.docx` 和已完成的 `artifact.md` 生成 `04_journal/example-journal/derived/manuscript.docx`。保留模板未涉及的 OOXML 部件，渲染所有页面并检查，不要覆盖英文主稿或官方模板。

投稿清洁：

> 请检查 `05_submission/` 的 DOCX 是否残留批注、修订、占位符、作者元数据或版式缺陷。保留原文件，输出新的 clean 版本和 QA 记录；不要自动批准 G4。

### 8.4 换刊

```bash
python3 -m paperflow journal-status \
  P-2026-001 old-journal superseded \
  --note "Rejected after review; retarget from approved English master"

python3 -m paperflow journal-init P-2026-001 \
  --journal "New Journal" \
  --article-type "Research Article" \
  --guidelines-url "https://new-journal.example/official-guidelines" \
  --verified-at "2026-09-01" \
  --template /absolute/path/new-template.docx
```

不要删除旧 profile，也不要把旧期刊派生稿复制成新期刊主稿。

---

## 9. 检查器与故障排查

### 9.1 常见错误代码

| 错误代码/信息 | 含义 | 安全恢复方式 |
| --- | --- | --- |
| `missing_source` | 登记的冻结源稿不存在 | 找回原冻结副本；不要用不确定版本冒充 |
| `source_hash_changed` | `00_source/` 文件被修改 | 保留异常文件，重新从可信原件以新文件名冻结；调查变更来源 |
| `template_hash_changed` | 官方模板副本被修改 | 从官方可信来源以新文件名重新登记；旧模板保留用于审计 |
| `missing_unit_id` / `duplicate_unit_id` | 翻译单元缺 ID 或重复 | 给单元分配唯一稳定 ID，不重排已有 ID |
| `missing_source_text` | 翻译单元没有中文源文 | 从冻结源稿定位并补回；不能凭记忆重写 |
| `translation_source_mismatch` | 单元的源稿哈希不属于已登记源稿 | 核对提取来源，不要混合不同版本 |
| `invalid_translation_status` | 使用了不支持的翻译状态 | 改为第 4.2 节允许值 |
| `missing_final_translation` | 已确认单元没有最终英文 | 补充英文或将状态退回 `review` |
| `translation_not_confirmed` | 翻译轨道完成但仍有未确认单元 | 逐项审核后再标记完成 |
| `incomplete_glossary_term` | 术语缺中文或首选英文 | 补齐字段 |
| `duplicate_glossary_term` | 同一中文术语重复 | 合并成一个条目并保留备选/禁用译法 |
| `unsupported_core_claim` | 核心结论没有证据 | 添加真实证据或降低/删除未经支持的结论 |
| `missing_evidence_link` | 结论引用了不存在的证据 ID | 修正 ID 或补充证据记录 |
| `duplicate_bibtex_key` | BibTeX key 重复 | 在文献管理器中分配唯一 key 并更新引用映射 |
| `unresolved_citekey` | 正文引用 key 不在 `library.bib` | 导入文献条目或修正 citekey |
| `missing_template` | 期刊模板记录存在但文件缺失 | 从已核验来源恢复，不要用其他期刊模板替代 |
| `comments_present` | 投稿 DOCX 有批注 | 保留审阅版，另生成无批注 clean 版本 |
| `tracked_changes_present` | 投稿 DOCX 有修订痕迹 | 保留 redline，另生成接受修订后的 clean 版本 |
| `placeholder_present` | 存在 TODO/TBD/XXX/`[[...]]` | 完成内容或明确移除占位符 |
| `identity_metadata` | 盲审稿含作者元数据 | 在副本上清除元数据并重新检查 |
| `missing_journal_profile` | G2 后没有且仅有一个活动期刊 | 激活正确 profile 或先处理重复活动期刊 |

### 9.2 常见命令错误

**`Unknown paper`**：使用 `P-2026-001` 或完整目录名，检查是否在正确的论文中心运行。

**`Refusing to overwrite frozen source`**：这是保护机制。新版原稿应使用新文件名登记，不要删除旧文件。

**`Select exactly one frozen source with --source-name`**：登记了零个或多个源稿。先冻结源稿，或用 `--source-name` 明确选择。

**`Translation extraction currently requires a valid DOCX source`**：当前自动提取不支持 PDF、旧 `.doc` 或损坏 DOCX。先保留原件，再制作可验证的 DOCX 工作副本。

**`Illegal status transition`**：按第 5.1 节进入合法中间状态。

**`Cannot approve Gx before Gy`**：前置人工关卡尚未批准。

**`Gx readiness failed`**：关卡顺序正确，但实际文件或 QA 证据不足。按错误信息补齐，不要手工把 `approved` 改成 `true`。

### 9.3 检查边界

即使 `check` 输出 PASS，也仍需人工确认：

- 翻译是否忠实且符合领域表达；
- 数值、单位、图表和统计结论是否正确；
- 期刊要求是否来自当前官方页面；
- Word 页面是否全部视觉正常；
- 投稿系统中的元数据是否与稿件一致。

---

## 10. 案例 A：中文旧稿翻译并投稿

本案例只展示虚构路径和预期输出，不应原样用于真实投稿。

### A1. 建项

```bash
python3 -m paperflow new \
  --title "城市街区形态对热环境的影响" \
  --slug urban-form-heat \
  --entry existing_chinese \
  --year 2026
```

预期输出：

```text
/.../papers/P-2026-001-urban-form-heat
```

初始总体状态为 `drafting`，翻译轨道为 `not_started`，下一关卡为 G0。

### A2. 冻结并提取中文源稿

```bash
python3 -m paperflow freeze-source \
  P-2026-001 /absolute/path/urban-heat-zh.docx

python3 -m paperflow extract-docx P-2026-001
```

预期：源稿复制到 `00_source/`；`segments.jsonl` 出现稳定单元；翻译轨道变为 `in_progress`。

如果直接再提取，会得到拒绝覆盖错误。这是为了保护已经开始的翻译。

### A3. 批准 G0 并进入翻译

```bash
python3 -m paperflow approve-gate P-2026-001 G0 \
  --note "中文主稿及需翻译附件范围已人工确认"

python3 -m paperflow set-status P-2026-001 translating
```

### A4. 翻译和术语审校

人工或由 Agent 协助编辑：

- `02_translation/glossary.yaml`；
- `02_translation/segments.jsonl` 的 `candidate_en`、`final_en`、风险和状态。

每个最终采用的单元应为 `confirmed` 且有非空 `final_en`。语言润色不得静默改变数据、单位、引用或不确定性。

将经确认内容生成：

```text
03_manuscript/master_en.docx
```

然后：

```bash
python3 -m paperflow set-track P-2026-001 translation_status complete
python3 -m paperflow set-track P-2026-001 manuscript_status complete
python3 -m paperflow set-status P-2026-001 language_review
python3 -m paperflow approve-gate P-2026-001 G1 \
  --note "英文主稿、全部翻译单元和术语已人工核对"
```

如果有单元未确认或缺少 `master_en.docx`，G1 会拒绝通过。

### A5. 建立目标期刊

```bash
python3 -m paperflow set-status P-2026-001 journal_targeting

python3 -m paperflow journal-init P-2026-001 \
  --journal "Journal of Example Studies" \
  --article-type "Original Article" \
  --guidelines-url "https://journal.example/official-guidelines" \
  --verified-at "2026-07-16" \
  --template /absolute/path/official-template.docx

python3 -m paperflow approve-gate P-2026-001 G2 \
  --note "期刊、文章类型和官方要求已核验"

python3 -m paperflow set-status P-2026-001 formatting
```

### A6. 派生期刊稿并完成 QA

完成 `artifact.md`，从英文主稿生成：

```text
04_journal/journal-of-example-studies/derived/manuscript.docx
```

运行结构检查：

```bash
python3 -m paperflow docx-audit \
  papers/P-2026-001-urban-form-heat/04_journal/journal-of-example-studies/derived/manuscript.docx \
  --blind-review
```

完成真实结构证据和全页渲染人工检查后登记：

```bash
python3 -m paperflow journal-qa \
  P-2026-001 journal-of-example-studies structural_audit pass \
  --evidence "04_journal/journal-of-example-studies/qa/structure.md"

python3 -m paperflow journal-qa \
  P-2026-001 journal-of-example-studies render_review pass \
  --reviewer "Human Reviewer" \
  --evidence "04_journal/journal-of-example-studies/qa/render-review.md"

python3 -m paperflow set-status P-2026-001 internal_review
python3 -m paperflow approve-gate P-2026-001 G3 \
  --note "科学内容、引用、结构和全部页面已人工确认"
```

### A7. 投稿包与 G4

把最终清洁文件放入 `05_submission/`，例如：

```text
manuscript-blind.docx
title-page.docx
cover-letter.docx
highlights.docx
```

实际文件以活动期刊 `required_submission_files` 为准。

```bash
python3 -m paperflow set-status P-2026-001 ready_to_submit
python3 -m paperflow check --paper P-2026-001
python3 -m paperflow approve-gate P-2026-001 G4 \
  --note "投稿包、匿名信息和 Word 全页版式已人工确认"
python3 -m paperflow set-status P-2026-001 submitted
```

### A8. 审稿和返修

收到审稿意见后创建：

```text
06_reviews/round-01/
├── editor-letter.pdf
├── reviewer-comments.md
├── response-to-reviewers.docx
└── revised-manuscript.docx
```

保留原始来信，不覆盖首次投稿包。

```bash
python3 -m paperflow set-status P-2026-001 under_review
python3 -m paperflow set-status P-2026-001 revision
python3 -m paperflow approve-gate P-2026-001 G5 \
  --note "逐条回复和返修稿已人工确认，可以提交本轮返修"
```

注意：当前 G5 自动条件只检查是否存在审稿轮次目录；回复质量仍必须人工审阅。

---

## 11. 案例 B：从研究问题开始写新论文

### B1. 建项与研究问题

```bash
python3 -m paperflow new \
  --title "Urban morphology and pedestrian thermal exposure" \
  --slug morphology-exposure \
  --entry new_research \
  --year 2026
```

新项目初始状态为 `idea`，研究轨道为 `in_progress`。

编辑 `01_research/research-question.md`，至少写明：

- 可证伪研究问题；
- 研究范围与对象；
- 主要假设；
- 可用数据与方法；
- 主要评价指标；
- 伦理、隐私和资源约束；
- 当前不确定性。

然后：

```bash
python3 -m paperflow approve-gate P-2026-001 G0 \
  --note "研究问题、范围和可行性已人工确认"
python3 -m paperflow set-status P-2026-001 exploring
```

### B2. 文献、证据和研究推进

把文献写入 `references/library.bib`，引用位置写入 `citations.jsonl`，证据和核心结论分别写入 `evidence.jsonl` 与 `claims.jsonl`。

调研和实验材料放入 `01_research/`，但不要把未经验证的 Agent 摘要当成证据。

```bash
python3 -m paperflow check --paper P-2026-001
python3 -m paperflow set-status P-2026-001 drafting
```

### B3. 英文主稿与 G1

新研究路径可以直接用英文写作，不要求 `segments.jsonl` 中存在中文翻译单元，但仍必须生成：

```text
03_manuscript/master_en.docx
```

```bash
python3 -m paperflow set-track P-2026-001 research_status complete
python3 -m paperflow set-track P-2026-001 manuscript_status complete
python3 -m paperflow approve-gate P-2026-001 G1 \
  --note "英文权威主稿及科学表达已人工确认"
```

### B4. 期刊、格式和投稿

后续与案例 A 相同：

```bash
python3 -m paperflow set-status P-2026-001 journal_targeting
python3 -m paperflow journal-init P-2026-001 \
  --journal "Example Research Journal" \
  --article-type "Research Article" \
  --guidelines-url "https://journal.example/official-guidelines" \
  --verified-at "2026-07-16" \
  --template /absolute/path/template.docx
python3 -m paperflow approve-gate P-2026-001 G2 --note "目标期刊要求已人工确认"
python3 -m paperflow set-status P-2026-001 formatting
```

完成派生稿、结构 QA 和全页渲染 QA 后进入 `internal_review` 并批准 G3；准备 `05_submission/` 后进入 `ready_to_submit` 并批准 G4。

即使新研究没有中文翻译，证据、引用、期刊要求、Word 结构和视觉检查仍然不能省略。

---

## 12. 日常使用清单

### 新建中文旧稿项目

- [ ] `new --entry existing_chinese`
- [ ] `freeze-source`
- [ ] `extract-docx`
- [ ] 人工批准 G0
- [ ] 填写术语和逐段翻译
- [ ] 生成并审阅 `master_en.docx`
- [ ] 人工批准 G1

### 新建研究项目

- [ ] `new --entry new_research`
- [ ] 填写 `research-question.md`
- [ ] 人工批准 G0
- [ ] 登记文献、证据、结论和实验
- [ ] 生成并审阅 `master_en.docx`
- [ ] 人工批准 G1

### 期刊与投稿

- [ ] 官方要求和模板已核验并记录日期
- [ ] `journal-init`
- [ ] 人工批准 G2
- [ ] 完成 `artifact.md`
- [ ] 从英文主稿派生期刊稿
- [ ] DOCX 结构审计
- [ ] 模板差异检查
- [ ] 全部页面人工视觉检查
- [ ] `journal-qa` 记录真实证据
- [ ] 人工批准 G3
- [ ] 准备并检查 `05_submission/`
- [ ] 人工批准 G4
- [ ] 外部投稿后更新状态

### 每周组合检查

```bash
python3 -m paperflow check --all
python3 -m paperflow rebuild
```

然后查看 [`papers/STATUS.md`](../papers/STATUS.md)，逐篇处理错误、阻塞项和下一关卡。
