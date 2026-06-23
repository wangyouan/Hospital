# Hospital 项目 — 服务器端 CLAUDE.md

> 放置位置：服务器工作目录根部，重命名为 `CLAUDE.md`：
> `/data/disk4/workspace/projects/hospital/CLAUDE.md`
> 本文件是给**服务器端 Claude** 的常驻指令。

---

## 一、角色分工（重要）

本项目由两个 thread 协作：

| 端 | 角色 |
|----|------|
| **本机（Cowork）** | 设计研究、**生成 prompt**、检查结果、分析数据 |
| **服务器（你）** | **执行 prompt**、抓取/下载/标注/回归、整理数据、回报产物 |

你（服务器端）**不负责**定研究问题或写 prompt。你的任务是：拿到本机给的 prompt → 严格执行 → 产出可核对的文件 → 简要回报关键指标，供本机检查。遇到歧义先记录并按最稳妥方式执行，不擅自扩大范围。

---

## 二、工作流程：严格三步走（每个改动都遵守）

1. **先写 vibe notes 并 commit**
   - 在 `/data/disk4/workspace/vibe_notes/hospital/` 新建本次笔记
     （命名 `YYYY-MM-DD-NN-<slug>.md`），写明：本次目标、采用的方案、脚本设计要点、对应的 prompt 出处。
   - 先 `git commit` 这份 notes。
2. **写代码** —— 实现脚本。
3. **代码写完 commit** —— 脚本 + 首次运行日志一并 `git commit`。

> 即：每个改动 = 先记 notes 并提交 → 实现 → 提交实现。生成脚本时按此节奏组织。

---

## 三、路径速查

```
# vibe notes（先记笔记、再提交）
/data/disk4/workspace/vibe_notes/hospital

# 工作目录（代码 + 数据产物）
/data/disk4/workspace/projects/hospital

# 现有 CBA 资产（来自 union_glassdoor，按需复制到 hospital，勿原地改旧项目）
/data/disk4/workspace/projects/union_glassdoor/outputs/20260622/cba/
    cba_manifest_full.csv      # 13,624 条全量元数据
    manifest_pages/*.jsonl     # 分页 checkpoint
    pdfs/  done.txt  download_failures.log
```

---

## 四、服务器执行约束（API 质量低，无法跑长任务，务必遵守）

- **断点续跑**：所有批处理（下载/抓取/LLM 标注/BERT 推理/回归网格）写 checkpoint，每 N 条 flush，中断后可补齐重跑。`done.txt` 之类的进度文件每完成一条立刻 append + flush。
- **切小步**：长任务拆成多个**可单独运行、单独产出文件**的 step，避免单脚本跑数小时。
- **失败隔离**：每个外部调用包 `try/except` + 超时 + 指数退避（最多 5 次）。最终失败写单独日志文件，**绝不中断主循环**。
- **并发克制**：并发数小（≤4），请求间加 sleep；遇 429/5xx 退避加倍。
- **禁一次性大批量 LLM 调用**：推理/抓取分片存盘，可断点续跑。
- **本地优先**：能用 pandas / 本地文件完成的（去重、过滤、统计、校验）不调 API。

---

## 五、回报约定（跑完通知本机检查）

每个 step 跑完，回报这些便于本机核对的指标：
- 产物文件路径 + 行数/大小/文件数
- 成功 / 失败计数，失败原因分布（Top 几类错误）
- 是否需要二次重跑补齐
- 任何与 prompt 预期不符之处

不要把大文件内容贴回来；本机会按路径自行抽样核对。可链接/可定位的产物给出明确路径。

---

## 六、项目背景（一句话）

起点数据是 Cornell eCommons "Collective Bargaining Agreements" 社区的集体谈判协议（CBA），共 13,624 条。研究设计仍在本机端确定中；当前阶段以**数据获取与整理**为主。详细数据资产与子集特征见本机 `CLAUDE.md`（项目状态备忘录），本机会随 prompt 同步必要信息。

---

*本文件随项目推进由本机更新后同步到服务器。*
