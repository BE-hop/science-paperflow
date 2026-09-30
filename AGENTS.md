# Science Agent Guidance

继承 `../AGENTS.md` 与 `../career/AGENTS.md`。科研结论必须与证据绑定，明确引用、方法、版本、假设和不确定性；禁止伪造数据、来源或实验结果。初始阅读不得批量载入论文库或数据集。

## Paperflow Web 与 Agent

- 本地工作台只绑定 `127.0.0.1`；不得在未建立认证和安全审计前开放到局域网或公网。
- Web 层必须调用 `paperflow` Python 服务，不得把用户输入拼接成 Shell 命令。
- Agent 必须在 `.paperflow/jobs/<job-id>/workspace/` 的论文副本中工作；正式论文只能由受控应用器在用户接受后更新。
- Agent 不得修改 `PAPER.yaml`、冻结原稿、官方模板或投稿回执，不得批准 G0–G5，也不得把候选内容登记为人工确认结果。
- 新增 Web、服务或 Agent 能力时，同步更新本文件、项目 `README.md`、`papers/README.md` 和 `docs/USER_MANUAL.md`。

## HCI 文献阅读

- HCI 文献入口位于 `literature/hci/`，与 `papers/` 下的 Paperflow 投稿中心相互独立；不得把阅读资料写入 `PAPER.yaml` 或投稿工作区。
- `literature/hci/journals.yaml` 是六本期刊、本地目录、Notion 页面和 Zotero collection key 的机器可读索引。结构或链接变化时，必须同步更新该文件、模块 `README.md` 和对应期刊 `README.md`。
- 影响因子、频率、索引和开放获取信息必须记录来源、指标年度（如可确认）与核验日期；出版方仅展示当前值时不得臆测指标年度。
- 必须分开记录读者访问条件与作者费用。混合开放获取不等于全文免费，完全开放获取也不等于作者无需 APC。
- Zotero 负责文献元数据和附件管理；本地 `papers/` 仅保存用户合法取得的副本，不自动下载、不绕过付费墙、不重复导入。
- Agent 可以检索、去重、整理元数据和生成候选笔记，但不得声称用户已经阅读、确认结论或完成可信度评价。JIF 不得替代对单篇论文方法、样本、证据和局限的判断。

## GitHub 公开发布边界

- 本项目公开仓库仅发布 Paperflow 工具代码、测试、通用模板与公开使用文档。
- `papers/P-*/` 中的论文工作区、`literature/` 中的阅读资料、`.paperflow/` Agent 作业以及本地缓存不得提交或推送。
- 发布前必须检查 `git status`、暂存文件清单和敏感信息扫描结果；不得仅依赖文件名判断资料是否可公开。
- `.gitignore` 是最低保护边界；如果新增论文、数据、附件或阅读模块，应先更新忽略规则再执行 Git 操作。
