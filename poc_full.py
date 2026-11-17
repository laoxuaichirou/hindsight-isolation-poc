# Hindsight 隔离 POC 全量判据测试
# 36 样本（A 工程 18 / B 营销 18）+ 噪声 6 + 无关查询 6 + 跨库泄漏 8 + 幽灵删除测试
# 判据：泄漏=0（跨库 recall 不得返回对方库事实）；无关查询 ≥5/6 返空（默认 + min_scores 两档）
import json, time, sys, traceback
from hindsight_client import Hindsight

c = Hindsight(base_url="http://127.0.0.1:18899", timeout=300)
R = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "samples": [], "recalls": [], "errors": []}

A = [
 "Project Alpha uses PostgreSQL 16 with pgvector for embeddings.",
 "The deploy target for Project Alpha is a Windows server at 192.168.1.50.",
 "Alpha's API gateway is Kong running on port 8000.",
 "Alpha stores user uploads in MinIO bucket alpha-uploads.",
 "The Alpha backend is FastAPI with Python 3.12.",
 "Alpha CI runs on GitHub Actions with a self-hosted runner named alpha-runner-01.",
 "Alpha's staging database is refreshed every Sunday at 03:00 from production snapshot.",
 "The Alpha team decided to drop Redis caching in favor of PostgreSQL materialized views.",
 "Alpha's monitoring stack is Prometheus plus Grafana on port 3000.",
 "Alpha uses JWT tokens with a 15-minute expiry and refresh rotation.",
 "The Alpha search feature uses BM25 via PostgreSQL full-text search.",
 "Alpha's backup policy keeps 30 daily snapshots in cold storage.",
 "Alpha rate limits public API to 100 requests per minute per key.",
 "The Alpha frontend is Next.js 15 deployed on Vercel.",
 "Alpha's error tracking is Sentry with project slug alpha-web.",
 "Alpha database migrations are managed with Alembic.",
 "Alpha's load test target is 500 concurrent users at p95 under 300ms.",
 "Alpha secrets live in a .env file excluded from git, rotated quarterly.",
]
B = [
 "Project Beta launch campaign targets Bilibili tech reviewers.",
 "Beta's November marketing budget is 5000 CNY.",
 "Beta's brand color is Klein blue with a green sprout logo.",
 "Beta publishes tutorial videos every Tuesday and Friday.",
 "Beta's tagline is 'AI tools for everyday creators'.",
 "Beta's landing page is dream3d.example with a waitlist form.",
 "Beta's influencer shortlist has 12 creators, top one is 老许爱吃肉丶.",
 "Beta's email newsletter goes out on the first Monday of each month.",
 "Beta's pricing page shows three tiers: free, pro 29 CNY, team 99 CNY.",
 "Beta's launch date is December 1st 2026.",
 "Beta's ad creatives must avoid the bottom 12 percent of the frame due to platform overlay.",
 "Beta's competitor analysis covers three tools: ToolX, ToolY, ToolZ.",
 "Beta's referral program gives 7 days of pro for each invited friend.",
 "Beta's customer interviews are recorded with consent and stored for 90 days.",
 "Beta's social calendar is managed in a shared Feishu sheet.",
 "Beta's video thumbnails use 16:9 with bold Chinese title text burned in.",
 "Beta's churn survey asks one question: what almost stopped you from subscribing.",
 "Beta's partnership with a GPU cloud gives community members free credits.",
]
NOISE = [
 "haha ok", "brb lunch", "asdf test 123", "the the the", "lol nice", "wait what",
]

def retain(bank, content, ctx, tag):
    t0 = time.time()
    try:
        r = c.retain(bank, content, context=ctx)
        R["samples"].append({"bank": bank, "tag": tag, "ok": bool(r.success), "items": r.items_count, "secs": round(time.time()-t0,1)})
        return r
    except Exception as e:
        R["samples"].append({"bank": bank, "tag": tag, "ok": False, "error": str(e)[:300], "secs": round(time.time()-t0,1)})
        R["errors"].append(f"retain {bank} {tag}: {str(e)[:200]}")
        return None

for i, s in enumerate(A): retain("poc-a", s, "engineering", f"A{i+1:02d}")
for i, s in enumerate(B): retain("poc-b", s, "marketing", f"B{i+1:02d}")
for i, s in enumerate(NOISE): retain("poc-a", s, "chat noise", f"N{i+1}")

def recall(bank, q, kind, min_scores=None):
    t0 = time.time()
    try:
        kw = {}
        if min_scores: kw["min_scores"] = min_scores
        r = c.recall(bank, q, max_tokens=1024, budget="low", **kw)
        items = [{"text": (x.text or "")[:140], "final": round(getattr(x.scores,"final",0) or 0, 4), "semantic": round(getattr(x.scores,"semantic",0) or 0, 4)} for x in (r.results or [])]
        R["recalls"].append({"bank": bank, "q": q, "kind": kind, "min_scores": min_scores, "n": len(items), "secs": round(time.time()-t0,2), "items": items})
        return items
    except Exception as e:
        R["recalls"].append({"bank": bank, "q": q, "kind": kind, "error": str(e)[:200]})
        R["errors"].append(f"recall {bank} {q[:30]}: {str(e)[:150]}")
        return []

# 跨库泄漏探针：A 库问 B 的事实，B 库问 A 的事实（各4）
LEAK = [
 ("poc-a", "What is Project Beta's marketing budget?", "B"),
 ("poc-a", "When is Project Beta's launch date?", "B"),
 ("poc-a", "What is Beta's brand color?", "B"),
 ("poc-a", "Who is on Beta's influencer shortlist?", "B"),
 ("poc-b", "What database does Project Alpha use?", "A"),
 ("poc-b", "What port is Alpha's API gateway on?", "A"),
 ("poc-b", "What is Alpha's deploy server IP?", "A"),
 ("poc-b", "What CI runner does Alpha use?", "A"),
]
for bank, q, other in LEAK:
    recall(bank, q, f"leak_default_from_{other}")
    recall(bank, q, f"leak_minscore_from_{other}", min_scores={"final": 0.5})

# 无关查询 6（默认 + min_scores）
IRR = [
 "What is the airspeed velocity of an unladen swallow?",
 "How do I bake a sourdough bread at home?",
 "Who won the 1998 FIFA World Cup final?",
 "What is the capital of Mongolia?",
 "Explain quantum chromodynamics in one sentence.",
 "What year did the Titanic sink?",
]
for q in IRR:
    recall("poc-a", q, "irrelevant_default")
    recall("poc-a", q, "irrelevant_minscore", min_scores={"final": 0.5})

# 相关查询 6（验证召回质量）
REL = [
 ("poc-a", "What database and vector extension does Alpha use?"),
 ("poc-a", "How are Alpha's secrets managed?"),
 ("poc-a", "What is Alpha's rate limit?"),
 ("poc-b", "What is Beta's pricing?"),
 ("poc-b", "What is Beta's launch date?"),
 ("poc-b", "What are Beta's thumbnail rules?"),
]
for bank, q in REL: recall(bank, q, "relevant")

# 幽灵删除测试：取 A 库一条 memory id，update_mode 删除/失效后 recall 是否仍返回
try:
    lm = c.list_memories("poc-a", limit=100)
    items = lm.items or []
    R["list_a_total"] = lm.total
    R["list_a_count"] = len(items)
    # find the IP fact
    target = None
    for it in items:
        txt = getattr(it, "content", None) or getattr(it, "text", "") or ""
        if "192.168.1.50" in txt:
            target = it; break
    if target is not None:
        mid = getattr(target, "id", None) or getattr(target, "memory_id", None)
        R["ghost_target_id"] = str(mid)
        # try invalidate via update_memory if available
        try:
            import asyncio
            from hindsight_client_api.models.update_memory_request import UpdateMemoryRequest
            asyncio.run(c.memory.update_memory("poc-a", str(mid), UpdateMemoryRequest(state="invalidated")))
            R["ghost_invalidate"] = "called"
        except Exception as e:
            R["ghost_invalidate"] = f"failed: {str(e)[:200]}"
        time.sleep(2)
        after = recall("poc-a", "What is Alpha's deploy server IP?", "ghost_after_invalidate")
        R["ghost_still_returned"] = any("192.168.1.50" in x["text"] for x in after)
    else:
        R["ghost_target_id"] = "not found in list"
except Exception as e:
    R["errors"].append(f"ghost test: {str(e)[:250]}")

# 噪声是否入库/可召回
noise_recall = recall("poc-a", "haha ok brb lunch asdf", "noise_probe")
R["noise_returned"] = len(noise_recall)

R["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
ok_samples = sum(1 for s in R["samples"] if s.get("ok"))
R["summary"] = {
 "samples_total": len(R["samples"]), "samples_ok": ok_samples,
 "recalls_total": len(R["recalls"]),
 "leak_default_hits": sum(1 for r in R["recalls"] if r["kind"].startswith("leak_default") and r.get("n",0) > 0),
 "leak_minscore_hits": sum(1 for r in R["recalls"] if r["kind"].startswith("leak_minscore") and r.get("n",0) > 0),
 "irrelevant_default_empty": sum(1 for r in R["recalls"] if r["kind"]=="irrelevant_default" and r.get("n",0)==0),
 "irrelevant_minscore_empty": sum(1 for r in R["recalls"] if r["kind"]=="irrelevant_minscore" and r.get("n",0)==0),
 "relevant_nonempty": sum(1 for r in R["recalls"] if r["kind"]=="relevant" and r.get("n",0)>0),
 "errors": len(R["errors"]),
}
with open("poc_full_results_20261117.json", "w", encoding="utf-8") as f:
    json.dump(R, f, ensure_ascii=False, indent=1)
print(json.dumps(R["summary"], ensure_ascii=False, indent=1))
print("ghost_still_returned:", R.get("ghost_still_returned"))
print("noise_returned:", R.get("noise_returned"))
print("errors:", R["errors"][:5])