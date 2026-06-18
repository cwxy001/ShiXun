import sys; sys.path.insert(0, '.')
from app.services.search_adapter import web_search_raw
from app.services.web_search import search_web, format_for_ai_prompt
import time

# Test raw search
print("1. 底层搜索测试")
t0 = time.time()
results = web_search_raw("Python教程", 3)
print(f"   耗时: {(time.time() - t0)*1000:.0f}ms, 找到 {len(results)} 条")
for r in results:
    title = r.get("title", "")[:80]
    url = r.get("url", "")[:80]
    snippet = r.get("snippet", "")[:120]
    print(f"   [{title}]")

# Test full pipeline
print("\n2. 搜索 + 格式化测试")
t0 = time.time()
sr = search_web("人工智能", 3)
print(f"   耗时: {(time.time() - t0)*1000:.0f}ms")
print(f"   结果数: {len(sr.get('results', []))}")
print(f"   来源: {sr.get('source')}")
print(f"   缓存: {sr.get('cached')}")

# Test AI prompt formatting
prompt = format_for_ai_prompt("人工智能", sr)
print(f"\n3. AI Prompt 长度: {len(prompt)} chars")
print(f"   包含参考来源: {'参考来源' in prompt}")
print(f"   以正确指令结尾: {prompt.endswith('并给出建议。')}")

print("\n全部通过" if len(sr.get('results', [])) > 0 else "搜索失败")
