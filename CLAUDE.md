# Hospital 项目 — 服务器端 CLAUDE.md

> `/data/disk4/workspace/projects/hospital/CLAUDE.md`
> 本文给**服务器端 Claude**，版本 v2（2026-06-23 post-download）。

---

## 一、角色分工（不变）

| 端 | 角色 |
|----|------|
| **本机（Cowork）** | 设计研究、**生成 prompt**、检查结果、分析数据 |
| **服务器（你）** | **执行 prompt**、抓取/下载/标注/回归、整理数据、回报产物 |

你**不负责**定研究问题或写 prompt。拿到 prompt → 严格执行 → 产出可核对文件 → 回报关键指标。歧义记录并按稳妥方式执行，不扩大范围。

---

## 二、工作流程（三步走）

1. **先写 vibe notes 并 commit** → `/data/disk4/workspace/vibe_notes/hospital/YYYY-MM-DD-NN-<slug>.md`
2. **写代码** → 实现脚本
3. **代码写完 commit** → 脚本 + 运行日志

---

## 三、当前数据资产

> 阶段一（数据获取）已完成。全部存储在 `data/cba/`（git 不跟踪）。

| 资产 | 路径 | 规模 |
|------|------|------|
| CBA 元数据 manifest | `data/cba/cba_manifest_full.csv` | 13,624 行 / 3.8MB |
| 全量 PDF | `data/cba/pdfs/{uuid}/{bs_uuid}.pdf` | 13,624 目录 / 34GB |
| Bitstream 映射（含 SHA256） | `data/cba/bitstream_map.csv` | 13,624 行 / 2.2MB |
| 进度文件 | `data/cba/done.txt` | 13,624 行 |
| Manifest 分页 checkpoint | `data/cba/manifest_pages/*.jsonl` | 137 页 |

**PDF 已全部下载，零失败。下一阶段无需再访问 Cornell API。**

路径速查：
```
# vibe notes
/data/disk4/workspace/vibe_notes/hospital

# 工作目录
/data/disk4/workspace/projects/hospital
/data/disk4/workspace/projects/hospital/scripts/          # 脚本
/data/disk4/workspace/projects/hospital/data/cba/          # 数据（34GB）
/data/disk4/workspace/projects/hospital/outputs/YYYYMMDD/  # 产物
/data/disk4/workspace/projects/hospital/scratch/           # 临时文件
/data/disk4/workspace/projects/hospital/logs/              # 日志
/data/disk4/workspace/projects/hospital/archive/           # 旧版 CLAUDE.md 备份
```

---

## 四、服务器执行约束

- **断点续跑**：所有批处理写 checkpoint，每 N 条 flush。中断后可补齐重跑。
- **切小步**：长任务拆成多个**可单独运行、单独产出文件**的 step。
- **失败隔离**：每个外部调用包 `try/except` + 超时 + 指数退避（最多 5 次）。失败写日志，**不中断主循环**。
- **并发克制**：并发 ≤ 4，请求间加 sleep；遇 429/5xx 退避加倍。
- **禁一次性大批量 LLM 调用**：推理/标注分片存盘，可断点续跑。
- **本地优先**：能用 pandas / 本地文件完成的（去重、过滤、统计、校验）不调 API。

---

## 五、回报约定

每个 step 跑完回报：
- 产物文件路径 + 行数/大小/文件数
- 成功 / 失败计数，失败原因分布
- 是否需要二次重跑补齐
- 任何与 prompt 预期不符之处

不贴大文件内容，本机按路径自行抽样核对。

---

## 六、项目状态

- **阶段一（数据获取）** ✅ 完成 — 13,624 条 CBA PDF 全部下载，零失败
- **阶段二** — 待本机 Prompt 02（文本提取 / PDF 解析 / 分类标注）
- 研究问题由本机端设计，服务器端不自行扩展分析方向

---

*旧版 CLAUDE.md 备份在 `archive/CLAUDE_20260623_v1.md`*
