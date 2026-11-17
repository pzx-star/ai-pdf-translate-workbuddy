# -*- coding: utf-8 -*-
"""检测本机是否安装 Adobe Illustrator（查注册表 ProgID，不启动应用、无副作用）。

用法:
    python check_illustrator.py

输出:
    ILLUSTRATOR_INSTALLED=True/False
    PROGID=Illustrator.Application     （安装时）
    VERSION=Adobe.Illustrator.XX       （安装时，ProgID 默认值）

退出码: 0 = 已安装, 1 = 未安装。

技能路由规则（SKILL.md「路线判定」）：
- 输入 .pdf 且已安装 Illustrator → 先转 .ai 再走 AI 流程（可编辑 .ai + 转曲 PDF + 台账）
- 输入 .pdf 且未安装 Illustrator → 走 PDF 矢量路线（vector_redact_insert.py），
  输出为活文字 PDF——**没有 Illustrator 无法转曲**，交付说明/台账须注明"未转曲"
- 输入 .ai → 恒走 AI 流程（无 Illustrator 时无法处理，如实报错）
"""
import sys

import winreg


def find_illustrator():
    for hive, subkey in ((winreg.HKEY_CLASSES_ROOT, 'Illustrator.Application'),
                         (winreg.HKEY_LOCAL_MACHINE,
                          r'SOFTWARE\Classes\Illustrator.Application')):
        try:
            with winreg.OpenKey(hive, subkey) as k:
                ver, _ = winreg.QueryValueEx(k, '')
                return {'installed': True, 'progid': subkey, 'description': ver}
        except OSError:
            continue
    return {'installed': False, 'progid': None, 'description': None}


if __name__ == '__main__':
    r = find_illustrator()
    print('ILLUSTRATOR_INSTALLED=%s' % r['installed'])
    if r['installed']:
        print('PROGID=%s' % r['progid'])
        print('VERSION=%s' % (r['description'] or 'unknown'))
    sys.exit(0 if r['installed'] else 1)
