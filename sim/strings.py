"""UI 文案单一来源。

所有显示在屏幕上的中文字串都在这里，**没有第二份**。

## 为什么必须单一来源

之前文案散在三处：`tools/pipeline/convert_font.py` 的 UI_STRINGS、
七个页面文档的线框图、inspector 原型的 JS 字面量。三处必然漂移，
而漂移的后果很具体：**字库没收的字在屏幕上是一片空白**，
且只有真机点亮才发现。

现在字库子集化从这里取字符集，页面文档从这里生成，验收平台从这里读。
改文案只改这一个文件。

## 排版约束

240px 宽、16×16 点阵 → 一行最多 **15 个汉字**（含边距）。
操作提示行要塞三个键，每键的动作词**不超过 2 字**（见 KEYS）。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 排版预算
# ---------------------------------------------------------------------------

SCREEN_W, SCREEN_H = 240, 320
GLYPH = 16
MARGIN = 4
MAX_CHARS_PER_LINE = (SCREEN_W - MARGIN * 2) // GLYPH      # 14
# 操作提示行：[A]xx [B]xx [C]xx —— 三组 × (方括号2 + 键1 + 动作2) = 15 字宽
KEY_HINT_MAX_ACTION = 2

# ---------------------------------------------------------------------------
# 三键提示
#
# 每个动作词严格 2 字 —— 不是美观要求，是**排版硬约束**：
# 三组提示要塞进 240px 一行。「切换榜单」这种 4 字词放不下，
# 所以 P7 用「切榜」。
#
# 动作词的选取原则：**说清会发生什么**，而不是说清这是什么功能。
# 「投球」比「捕获」好 —— 前者是玩家的动作，后者是系统的判定。
# ---------------------------------------------------------------------------

KEYS = {
    "P1": {"A": "照料", "B": "图鉴", "C": "遭遇"},
    "P2": {"A": "选中", "B": "返回", "C": "丢弃"},
    "P3": {"A": "捕获", "B": "战斗", "C": "逃跑"},
    "P4": {"A": "投球", "B": "换球", "C": "取消"},
    "P5": {"A": "执行", "B": "切换", "C": "返回"},
    "P6": {"A": "详情", "B": "翻页", "C": "返回"},
    "P7": {"A": "切榜", "B": "翻页", "C": "返回"},
    "P8": {"A": "确认", "B": "下个", "C": "上个"},     # 取名页（S12）
    "INTRO": {"A": "确认", "B": "移动", "C": "预览"},   # 伙伴选择（S11）
}

# ---------------------------------------------------------------------------
# 逐页文案
# ---------------------------------------------------------------------------

PAGES = {
    "P1": {
        "title": "待机",
        "labels": ["饱食", "心情", "体能", "今日行程"],
        # 「今日行程」是**抽象刻度，不标步数/公里** ——
        # 设备没有 IMU 也没有 GPS，给不出那种精度。
        # 说「行程」而不说「步数」，是不承诺做不到的事。
        "mood": ["愉快", "平静", "低落", "消沉"],
        "badge": "遭遇",              # C 键角标，后跟待处理数
        "empty": "今天还没遇到什么",
    },
    "P2": {
        "title": "刚才路上遇到",
        "hint": "稀有度越高越难捕获",
        "empty": "队列是空的",
        "biomes": ["野外", "住宅区", "办公区", "商业区", "交通枢纽"],
        "dropped": "队列满了，丢掉最旧的",
    },
    "P3": {
        "eff": {
            200: "效果绝佳",
            100: "",              # 正常倍率不提示 —— 只在有反差时说话
            50: "效果不好",
            0: "没有效果",
        },
        "result": {"win": "胜", "lose": "败"},
        "labels": ["回合", "经验"],
        "fled": "跑掉了",
        "weakened": "看起来虚弱了",   # 战后提示：这是「先打再抓」的因果反馈
    },
    "P4": {
        "title": "捕获",
        "balls": {"poke": "精灵球", "great": "超级球", "ultra": "高级球"},
        "hit": "命中",
        "miss": "未命中",
        "caught": "捕获成功",
        "fled": "跑掉了",
        "no_ball": "没有球了",
        "berry": "浆果",
    },
    "P5": {
        "title": "照料",
        "actions": ["喂食", "玩耍", "休息", "取名", "查看详情"],
        "labels": ["等级", "属性", "亲密度", "探索值", "进化"],
        "can_evolve": "可以进化了",
        "reunion": "好久不见",        # 长时间离线后的重逢
    },
    "P6": {
        "title": "图鉴",
        "labels": ["已捕获", "未捕获", "闪光"],
        "seen_only": "见过",          # 遇到但没抓到 —— 剪影 + 这个标记
    },
    "P7": {
        "title": "成绩",
        "boards": ["个人纪录", "累计", "近期趋势"],
        "records": ["单日遭遇最多", "单日移动量", "单日新地点",
                    "连续照料", "连续出门", "最稀有捕获", "闪光捕获"],
        "labels": ["第", "天", "共", "只"],
        "new_record": "新纪录",
        "milestone": "坚持了",        # 后跟天数
    },
    "P8": {
        "title": "取名",
        "groups": ["叠字", "属性", "单字", "称号"],
        "unnamed": "未命名",
        "keep": "保持原名",
    },
    "INTRO": {
        "title": "选择伙伴",
        "unknown": "？？？",           # 球未打开时
        "not_in_ball": "它不进球",     # 皮卡丘专属 —— 一句话说明为什么它在外面
        "confirm": "就决定是你了",
    },
}

# 通用词 —— 跨页面复用，单独列出避免各页重复定义
COMMON = {
    "yes": "是", "no": "否", "none": "无",
    "back": "返回", "confirm": "确认", "cancel": "取消",
    "level": "等级", "type": "属性",
}

# 属性名（初代 15 种，顺序与 gameplay.TYPES 一致）
TYPES_CN = ["一般", "火", "水", "电", "草", "冰", "格斗", "毒",
            "地面", "飞行", "超能", "虫", "岩石", "幽灵", "龙"]


# ---------------------------------------------------------------------------
# 字符集导出 —— 字库子集化的输入
# ---------------------------------------------------------------------------

def _walk(obj) -> list[str]:
    """递归收集所有字串。"""
    out: list[str] = []
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            out += _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out += _walk(v)
    return out


def all_strings() -> list[str]:
    """全部 UI 字串（含三键提示、逐页文案、通用词、属性名）。"""
    return _walk(KEYS) + _walk(PAGES) + _walk(COMMON) + list(TYPES_CN)


def charset() -> set[str]:
    """UI 用到的全部字符 —— 字库只需收这些。"""
    out: set[str] = set()
    for s in all_strings():
        out |= set(s)
    return out


# ---------------------------------------------------------------------------
# 排版校验 —— 这是这个文件存在的第二个理由
#
# 校验按**像素**算，不按字数算：汉字 16px、ASCII 8px。
# 只数汉字会在混排行上给出错误结论（「皮卡丘 Lv12 ♥ 78」是 14 个「字」
# 但只占 144px，而 14 个纯汉字要 224px）。
# ---------------------------------------------------------------------------

USABLE_W = SCREEN_W - MARGIN * 2         # 232px


def text_px(s: str) -> int:
    """字串宽度（像素）。汉字全宽 16，ASCII 半宽 8。"""
    return sum(GLYPH if c > "ÿ" else GLYPH // 2 for c in s)


def check_key_hints() -> list[str]:
    """三键提示是否放得下 —— 动作词 ≤2 字，且整行放得下。"""
    bad = []
    for page, keys in KEYS.items():
        for k, action in keys.items():
            if len(action) > KEY_HINT_MAX_ACTION:
                bad.append(f"{page}.{k} 「{action}」{len(action)} 字 "
                           f"> {KEY_HINT_MAX_ACTION}")
        line = " ".join(f"[{k}]{a}" for k, a in keys.items())
        px = text_px(line)
        # P1 的 C 键后还要挂角标数字，留出余量
        budget = USABLE_W - (24 if page == "P1" else 0)
        if px > budget:
            bad.append(f"{page} 提示行 {px}px > {budget}px：「{line}」")
    return bad


def check_line_widths() -> list[str]:
    """单行文案是否超宽（按像素）。返回违规项。"""
    bad = []
    for page, d in PAGES.items():
        for key, val in d.items():
            for s in _walk(val):
                px = text_px(s)
                if px > USABLE_W:
                    bad.append(f"{page}.{key} 「{s}」{px}px > {USABLE_W}px")
    return bad


def audit() -> dict:
    """全量排版审计 —— CI 与验收平台都跑这个。"""
    kb, lb = check_key_hints(), check_line_widths()
    widest = max(all_strings(), key=text_px)
    hints = {p: text_px(" ".join(f"[{k}]{a}" for k, a in ks.items()))
             for p, ks in KEYS.items()}
    return {
        "strings": len(all_strings()),
        "chars": len(charset()),
        "usable_px": USABLE_W,
        "widest": widest,
        "widest_px": text_px(widest),
        "hint_px": hints,
        "key_violations": kb,
        "line_violations": lb,
        "ok": not kb and not lb,
    }
