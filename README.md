# Science

用于科研论文、文献、研究方法、实验、数据分析与学术工作流工具。

## 当前项目

| Project | Purpose | Entry |
| --- | --- | --- |
| Paperflow | 多论文科研、中文稿翻译、SCI 期刊格式转换、投稿与返修管理 | 双击 `Start Paperflow.command` / `papers/README.md` |
| HCI 文献阅读 | HCI、3D、XR、虚拟交互与计算设计的期刊积累和三端索引 | [`literature/hci/README.md`](literature/hci/README.md) |

Paperflow 以每篇论文的 `PAPER.yaml` 为状态事实源，以 Markdown、YAML、JSONL 和原始文档文件保存可审计记录。原始论文、官方期刊模板和投稿回执不得覆盖或删除。

## 本地工作台

普通使用不需要记忆命令。双击 [`Start Paperflow.command`](<Start Paperflow.command>)，浏览器会打开只允许本机访问的论文工作台：

- 首页只显示每篇论文的当前阶段、阻塞项和一个“继续下一步”；
- 五阶段向导处理建项、论文内容、目标期刊、投稿和返修；
- 用户只负责选择、审核、人工批准和推进；
- 确定性文件操作由系统完成，复杂整理可点击“交给 Agent”；
- Agent 在隔离副本中生成候选结果，用户接受后才进入正式论文目录。

CLI 仍作为开发、自动化和故障排查入口，可运行 `python -m paperflow --help` 查看。

## 公开仓库范围

GitHub 公开版本包含 Paperflow 工具代码、自动测试、通用模板和使用文档。以下本地内容默认保密且被 `.gitignore` 排除：

- `papers/P-*/`：具体论文、研究问题、证据、引用和稿件；
- `literature/`：文献阅读索引、笔记与本地资料；
- `papers/.paperflow/`、`.paperflow/`：Agent 临时副本、任务输出与运行记录；
- Python 缓存、测试缓存、本地环境文件和日志。

公开仓库不是论文资料备份。需要备份未发表研究时，应使用权限明确的私有存储。

## HCI 文献阅读

[`literature/hci/`](literature/hci/) 是独立于“计算设计”和 Paperflow 投稿中心的文献积累模块。初版维护六本期刊，并把 Notion 研究页、Zotero 集合和本地目录对应起来。

- Notion 负责期刊信息、阅读流程和结构化笔记入口；
- Zotero 负责条目元数据、去重、引用和附件；
- 本地目录保存机器可读索引、阅读笔记和用户合法取得的论文副本；
- 期刊指标和开放获取信息使用带来源与核验日期的快照，正式投稿或批量检索前应重新核验。

详细规则、期刊入口和维护方式见 [`literature/hci/README.md`](literature/hci/README.md)。
