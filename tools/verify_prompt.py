"""验证管理端和用户端的数字员工 prompt 一致性"""
import sys; sys.path.insert(0, '.')
from app.models.digital_employee import DigitalEmployeeRepository
from app.models.db import get_connection
from app.controllers.digital_employee import build_employee_system_prompt
import json

emp = DigitalEmployeeRepository.get_by_id(7)
emp_dict = dict(emp)

prompt = build_employee_system_prompt(emp_dict)

print(f"员工: [{emp_dict['id']}] {emp_dict['name']}")
print(f"role_name: {emp_dict['role_name']}")
print(f"system_prompt: '{emp_dict['system_prompt']}'")
print(f"greeting: '{emp_dict['greeting']}'")
print()

checks = [
    ("包含身份", "你是西师妹" in prompt),
    ("包含角色设定", "角色设定" in prompt),
    ("技能能力列表标题", "你拥有以下技能能力" in prompt),
    ("技能详细定义标题", "各技能详细行为定义" in prompt),
    ("技能自述引导", "你有什么能力" in prompt),
    ("面试题库技能名", "面试题库" in prompt),
    ("SQL问数技能名", "SQL问数" in prompt),
    ("技能引导完整", prompt.endswith("当用户的问题匹配某个技能时，请使用该技能定义的角色和能力来回答。")),
]

all_ok = True
for name, result in checks:
    status = "PASS" if result else "FAIL"
    if not result: all_ok = False
    print(f"  [{status}] {name}")

print(f"\n结果: {'全部通过' if all_ok else '存在失败'}")
if not all_ok:
    sys.exit(1)
