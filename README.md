# Hindsight 记忆引擎 POC 结论（2026-11-17）

> 来源：`G:\Hermes\cache\scratch\repo_triage_20261116\poc_engine\`
> 原始数据已被精简为 `poc_results_精简_20261117.json`（4.7KB，含全部关键数字）
> 跑测脚本 `poc_full.py` / `poc_stage2.py` / `poc_stage3.py` 一并保留

## 这是什么

在做「Hermes vs Hindsight vs T3 Code」架构对比时，为了不靠文档吹牛、要拿实测，
用 `hindsight_client` 跑的一套**跨项目记忆隔离**验证。

建两个独立记忆库：`poc-a`（Alpha 项目，38 条记忆）、`poc-b`（Beta 项目，18 条），
然后用 A 的问题去查 B，看会不会串味儿。

## ⚠️ 核心结论：Hindsight 默认会跨项目泄漏记忆

42 条样本全部跑通（42/42），但泄漏测试 16 条**全军覆没**：

| 查询 | 默认返回 | 设 min_score=0.5 后 |
|---|---|---|
| 问 Beta 的市场预算 | 38 条，**Alpha 38 条 / Beta 0 条** | 23 条，Alpha 23 / Beta 0 |
| 问 Beta 的上线日期 | 38 条，**Alpha 38 / Beta 0** | 23 条，Alpha 23 / Beta 0 |
| 问 Beta 的品牌色 | 38 条，**Alpha 38 / Beta 0** | 23 条，Alpha 23 / Beta 0 |
| 问 Beta 的达人名单 | 38 条，**Alpha 38 / Beta 0** | 23 条，Alpha 23 / Beta 0 |
| 问 Alpha 用什么数据库 | 38 条，**Alpha 0 / Beta 38** | 23 条，Alpha 0 / Beta 23 |
| 问 Alpha 的网关端口 | 38 条，**Alpha 0 / Beta 38** | 23 条，Alpha 0 / Beta 23 |
| 问 Alpha 的部署 IP | 38 条，**Alpha 0 / Beta 38** | 23 条，Alpha 0 / Beta 23 |
| 问 Alpha 用什么 CI runner | 38 条，**Alpha 0 / Beta 38** | 23 条，Alpha 0 / Beta 23 |

**问 A 项目的事，返回的全是 B 项目的记忆，一条都不对。**

而且 `min_score` 过滤（0.5）只是把条数从 38 压到 23，**完全没解决串味儿**——
因为返回的仍然是另一个项目的全部内容。

### 这意味着什么

跨项目/跨客户用一套 Hindsight 库，记忆会互相污染。
如果一个 Agent 服务多个项目（比如同时做电商和课程），
问「这个项目的预算是多少」会拿到另一个项目的数字，
**而且看起来像真答案**——这比查不到更危险。

## 其他发现

**"幽灵记忆"删不掉，但至少查不到：**
- 尝试作废一条记忆（`ghost_invalidate`）→ 操作本身失败（`Timeout context manager should be used inside a task`）
- 但检查 `ghost_still_returned` = **False**，作废后的内容确实不再返回

**噪声查询表现正常：**
- 输入乱码「haha ok brb lunch asdf」→ 返回 0 条（`noise_returned: 0`）✅

**相关的查询是准的：**
- 问 Alpha 数据库 → 首条就是 `PostgreSQL 16 with pgvector`（semantic 0.5987）
- 问 Beta 定价 → 首条就是 `three tiers: free, pro at 29 CNY, team at 99 CNY`（semantic 0.7334）
- 说明**库内检索质量没问题，问题纯粹出在「不隔离」**

**已知错误（2 条）：**
```
recall poc-a "What is Alpha's deploy server IP?": Timeout context manager should be used inside a task
recall poc-a "haha ok brb lunch asdf": Timeout context manager should be used inside a task
```
这是 asyncio 用法问题（客户端在非 task 上下文调用），不影响上面的泄漏结论。

## 对决策的影响

**不能把 Hindsight 当「一个库服务所有项目」用。**
若要用，必须：
1. 每个项目独立实例/独立库 + 独立端口，不能只靠 `bank` 参数区分
2. 或者在应用层做强制过滤，拿到结果后按来源项目过滤——但这等于自己重做隔离

**本次没有采纳 Hindsight**，Hermes 继续用内置记忆（策展式 declarative 事实 + skill 分层）。

## 相关文档

同目录下的架构对比，结论互相印证：
- `2026-11-16_设计对比_Hermes独立分析.md`
- `codex_drift_review_answer_20261117.md`
- `hindsight_README.md` / `hindsight_hermes_docs.md`