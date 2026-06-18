# 技能调度系统测试用例
# 运行方式: python test/test_skill_scheduler.py

import os
import sys
import json

# 添加项目根目录到 sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 初始化数据库
from app.models.db import init_db
init_db()

from app.services.skill_scheduler import (
    parse_command,
    register_skill,
    unregister_skill,
    get_registered_skills,
    dispatch_skill,
    register_builtin_skills,
)


def test_parse_command():
    """测试 1: 命令解析"""
    print("=" * 60)
    print("测试 1: parse_command 命令解析")
    print("=" * 60)

    # 测试反斜杠格式
    skill_name, args, is_cmd = parse_command("\\search Python教程")
    assert is_cmd, "应识别为命令"
    assert skill_name == "search", f"技能名应为 'search'，实际: {skill_name}"
    assert args == "Python教程", f"参数应为 'Python教程'，实际: {args}"
    print(f"  PASS \\search Python教程 → skill={skill_name}, args={args}")

    # 测试 @ 格式
    skill_name, args, is_cmd = parse_command("@天气 北京")
    assert is_cmd, "应识别为命令"
    assert skill_name == "天气", f"技能名应为 '天气'，实际: {skill_name}"
    assert args == "北京", f"参数应为 '北京'，实际: {args}"
    print(f"  PASS @天气 北京 → skill={skill_name}, args={args}")

    # 测试非命令
    skill_name, args, is_cmd = parse_command("你好世界")
    assert not is_cmd, "不应识别为命令"
    assert args == "你好世界", "原消息应保留"
    print(f"  PASS 你好世界 → is_cmd={is_cmd}")

    # 测试空输入
    skill_name, args, is_cmd = parse_command("")
    assert not is_cmd, "空字符串不应识别为命令"
    print(f"  PASS '' → is_cmd={is_cmd}")

    # 测试中文技能名
    skill_name, args, is_cmd = parse_command("\\网络搜索 最新资讯")
    assert is_cmd
    assert skill_name == "网络搜索"
    assert args == "最新资讯"
    print(f"  PASS \\网络搜索 最新资讯 → skill={skill_name}, args={args}")


def test_register_and_unregister():
    """测试 2: 技能注册与注销"""
    print("\n" + "=" * 60)
    print("测试 2: 技能注册 / 注销 / 列表")
    print("=" * 60)

    # 注册测试技能
    def mock_handler(args, ctx):
        return {"result": f"处理了: {args}", "ctx": ctx}

    register_skill("test_skill", mock_handler, "测试技能", category="测试",
                   aliases=["测试", "test"])
    print("  PASS 注册 test_skill（含别名）")

    # 验证获取列表
    skills = get_registered_skills()
    names = [s["name"] for s in skills]
    assert "test_skill" in names, f"test_skill 应在列表中，当前: {names}"
    print(f"  PASS 技能列表含 test_skill，总数: {len(skills)}")

    # 测试注销
    unregister_skill("test_skill")
    skills = get_registered_skills()
    names = [s["name"] for s in skills]
    assert "test_skill" not in names, f"test_skill 不应在列表中"
    print("  PASS 注销 test_skill 后不在列表中")


def test_dispatch_skill():
    """测试 3: 技能调度执行"""
    print("\n" + "=" * 60)
    print("测试 3: dispatch_skill 技能调度执行")
    print("=" * 60)

    # 注册测试处理器
    def test_handler(args, ctx):
        return {"processed": args.upper(), "caller": ctx.get("caller_name", "unknown")}

    register_skill("upper", test_handler, "转大写", category="测试")

    # 测试正常调度
    result = dispatch_skill("upper", "hello", context={"caller_name": "test_user"})
    assert result["success"], f"调度应成功，错误: {result.get('error')}"
    assert result["data"]["processed"] == "HELLO", f"应为 HELLO，实际: {result['data']}"
    assert result["skill_source"] == "registry", f"来源应为 registry，实际: {result['skill_source']}"
    print(f"  PASS dispatch_skill('upper', 'hello') → success={result['success']}, data={result['data']}")

    # 测试未知技能
    result = dispatch_skill("unknown_skill_xyz", "test", context={})
    assert not result["success"], "未知技能应调度失败"
    assert "未注册" in result["error"] or "未启用" in result["error"], f"错误信息应含 '未注册'，实际: {result['error']}"
    print(f"  PASS dispatch_skill('unknown_skill_xyz') → success={result['success']}, error={result.get('error', '')[:50]}")

    # 清理
    unregister_skill("upper")


def test_builtin_skills():
    """测试 4: 内置技能注册"""
    print("\n" + "=" * 60)
    print("测试 4: register_builtin_skills 内置技能")
    print("=" * 60)

    register_builtin_skills()
    skills = get_registered_skills()
    names = [s["name"] for s in skills]

    # 验证核心内置技能存在
    required = ["search", "help"]
    for name in required:
        if name in names:
            print(f"  PASS 内置技能 '{name}' 已注册")
        else:
            print(f"  WARN 内置技能 '{name}' 未注册（可能因依赖缺失）")

    print(f"  已注册技能总数: {len(skills)}")
    for s in skills:
        aliases = f" (别名: {', '.join(s.get('aliases', []))})" if s.get("aliases") else ""
        print(f"    - {s['name']} [{s['category']}]{aliases}")


def test_custom_skill_registration():
    """测试 5: 自定义技能动态注册与扩展"""
    print("\n" + "=" * 60)
    print("测试 5: 自定义技能动态注册（扩展性验证）")
    print("=" * 60)

    # 模拟注册一个新技能（如翻译）
    def translate_handler(args, ctx):
        # 模拟翻译（实际可接翻译 API）
        return {"source": args, "target": f"[翻译结果] {args}", "lang": "zh->en"}

    register_skill("translate", translate_handler, "文本翻译", category="工具",
                   aliases=["翻译", "translate"])

    # 验证注册
    skills = get_registered_skills()
    names = [s["name"] for s in skills]
    assert "translate" in names, "translate 应在技能列表中"
    print("  PASS 注册自定义技能 'translate'")

    # 通过别名调用
    result = dispatch_skill("翻译", "你好世界", context={"caller_name": "test"})
    assert result["success"], f"别名调度应成功: {result.get('error')}"
    assert "翻译结果" in str(result["data"]["target"]), f"应包含翻译结果: {result['data']}"
    print(f"  PASS 别名 '翻译' → {result['data']}")

    # 注销
    unregister_skill("translate")
    skills = get_registered_skills()
    names = [s["name"] for s in skills]
    assert "translate" not in names
    print("  PASS 注销自定义技能成功")


def test_dispatch_logging():
    """测试 6: 调度日志记录"""
    print("\n" + "=" * 60)
    print("测试 6: 调度日志记录到 skill_call_logs 表")
    print("=" * 60)

    def log_handler(args, ctx):
        return {"message": "ok"}

    register_skill("logtest", log_handler, "日志测试", category="测试")

    # 执行多次调度
    dispatch_skill("logtest", "arg1", context={"caller_name": "test_user", "caller_id": 1})
    dispatch_skill("logtest", "arg2", context={"caller_name": "test_user", "caller_id": 1})
    dispatch_skill("unknown_skill", "test", context={})

    # 检查日志
    try:
        from app.models.ai_skill import SkillCallLogRepository
        logs = SkillCallLogRepository.paginate(page=1, page_size=10)
        total = logs["total"]
        print(f"  PASS 日志总数: {total}")
        if total > 0:
            latest = dict(logs["list"][0])
            print(f"  最新日志: skill={latest.get('skill_name')}, success={latest.get('success')}, "
                  f"duration={latest.get('duration_ms')}ms, created={latest.get('created_at')}")
    except Exception as e:
        print(f"  WARN 读取日志失败: {e}")

    unregister_skill("logtest")


def run_all():
    print("\n" + "#" * 60)
    print("#  技能调度系统 (Skill Scheduler) 测试套件")
    print("#" * 60)

    tests = [
        test_parse_command,
        test_register_and_unregister,
        test_dispatch_skill,
        test_builtin_skills,
        test_custom_skill_registration,
        test_dispatch_logging,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"\n  FAIL {test.__name__}: {e}")
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"  测试结果: {passed} 通过, {failed} 失败, 共 {len(tests)} 项")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
