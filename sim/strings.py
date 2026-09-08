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
    "P0": {"A": "继续", "C": "跳过"},
    "P1": {"A": "照料", "B": "图鉴", "C": "遭遇"},
    "P2": {"A": "选中", "B": "下条", "C": "返回"},  # B 长按丢弃
    "P3": {"A": "捕获", "B": "战斗", "C": "返回"},
    "P4": {"A": "投球", "B": "换球", "C": "取消"},
    "P5": {"A": "执行", "B": "切换", "C": "返回"},
    "P6": {"A": "上页", "B": "下页", "C": "返回"},
    "P7": {"A": "切榜", "B": "翻页", "C": "返回"},
    "P8": {"A": "确认", "B": "下个", "C": "上个"},     # 取名页（S12）
    "INTRO": {"A": "确认", "B": "移动", "C": "预览"},   # 伙伴选择（S11）
}

# 键名 —— 从 KEYS 的字典键推导，不再写死一份。
#
# 这三个字形一度不在字库里：charset() 只收 KEYS 的 values，
# 键名（"A"/"B"/"C"）从没被收进去，于是九处提示行的键位标签全空白。
# 推导而非硬编码，是为了将来若改键名（比如加第四个键）不会再漏。
KEYS_LABELS = sorted({k for page in KEYS.values() for k in page})

# ---------------------------------------------------------------------------
# 战斗解说（P3）—— 模板，不是成品句
#
# 用户要求「不要说『我方』，用宝可梦的名字，像解说一样」。
# GSC 原作是 `<USER> used <MOVE>!`（pokecrystal 的 used_move_text.asm
# 与 common_2.asm:738），敌方带 `Enemy` 前缀（battle.asm:51）；
# 中文侧对应「野生的」。
#
# **这里只登记模板里的固定字**，物种名与招式名来自 gen1.bin / moves.bin
# 的名字池，那两个池子已经被 convert_font.py 单独收进字库。
#
# ## 为什么要单独列一个字集
#
# 「使」这个字曾经**两头都不在**：不在 charset()，也不在 font16.bin。
# 而「攻」侥幸在字库里，靠的是 battle.c:165 的一句**注释**「一次攻击」
# 被 convert_font.py 的固件源码扫描捞到 —— 有人整理注释删掉那行，
# 字就没了，且要等固件上屏才会暴露成空白方框。
#
# 兜底不是来源。上屏的字要在这里登记。
# ---------------------------------------------------------------------------

# ## 为什么是两行
#
# 单行放不下最坏组合（cep-coder 2026-09-06 实测发现并正确停下）：
#
#     野生多刺菊石兽使用了尖刺加农炮！ = 16 字 = 256px > 232px
#
# 151 只里 5 字名两只（三合一磁怪 / 多刺菊石兽），招式名最长 5 字
# （百万吨重拳），4 字及以上招式 29 个 —— 多刺菊石兽 Lv44 正好学
# 「尖刺加农炮」，所以这不是理论最坏而是实战可达。
#
# 缩前缀（「野生的」→「野生」）只省 16px，救不了这一类。
# **GSC 原作的消息窗本来就是两行** —— 拆行是回到原作形态，不是妥协。
# 拆后 112px / 144px 都很宽松。

BATTLE_LINES = {
    # 第一行：谁。第二行：做了什么。
    "who_wild": "野生{name}",             # 野生多刺菊石兽
    "who_pet": "{name}",                  # 皮卡丘
    "used": "使用了{move}！",             # 使用了尖刺加农炮！
    # 「{who}的攻击没有命中！」直译自 GSC，但中文里
    # 「野生的大岩蛇的攻击…」两个「的」读着累赘。用户选了这个说法。
    "missed": "的攻击落空了！",
}

# 占位符本身不上屏，别收进字库（每字形 32 字节）。
# 不用 re —— 这个文件保持零 import。
BATTLE_LINES_CHARS = "".join(
    ch for s in BATTLE_LINES.values() for ch in s
    if ch not in "{}" and not ch.isascii()
) + "！"


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
        "phase_hint": {"playing": "[A]捕获 [C]返回", "counter": "野生宝可梦正在反击",
                       "won": "[A]最后投球 [C]返回", "lost": "[C]返回"},
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
        "done_summary": ["已捕获", "图鉴 +1"],
        "counter": "捕获失败，准备反击",
        "last_chance": "战斗获胜，仅此一球",
    },
    "P5": {
        "title": "照料",
        "actions": ["喂食", "玩耍", "休息", "取名", "查看详情"],
        "labels": ["等级", "属性", "亲密度", "探索值", "进化"],
        "can_evolve": "可以进化了",
        "evolved": "进化了",
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
    """UI 用到的全部字符 —— 字库只需收这些。

    ## 为什么要单独加键名与提示行括号

    `KEYS` 用 "A"/"B"/"C" 作**字典键**，而 `_walk()` 只收 values ——
    于是 `A B C` 三个字形从没进过字库。而每个页面文档写的底部提示行是

        [A]照料 [B]图鉴 [C]遭遇

    键名和方括号全缺 → 八个页面加开场共九处提示行都渲染成
    「照料 图鉴 遭遇」，玩家不知道按哪个键。三键设备上这是致命的：
    没有屏幕外的键位标记，提示行是键位的**唯一**说明。

    这里不改 `_walk()` 去收 dict 键 —— `all_strings()` 还被排版校验用，
    往里塞键名会让「行宽是否超 232px」的计算多算三个字符。
    """
    out: set[str] = set()
    for s in all_strings():
        out |= set(s)
    # 三键提示行：键名（KEYS 的字典键）+ 方括号 + 分隔空格
    out |= set(KEYS_LABELS) | set("[] ")
    # 战斗解说的模板字（P3）—— 见 BATTLE_LINES 的说明
    out |= set(BATTLE_LINES_CHARS)
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
    """字串宽度（像素）。汉字全宽 16，ASCII 半宽 8。

    ⚠️ **这个模型与 assets/font16.bin 的实际格式不符** —— 见 text_px_fixed()。
    """
    return sum(GLYPH if c > "ÿ" else GLYPH // 2 for c in s)


def text_px_fixed(s: str) -> int:
    """字串宽度（像素），按**字库的实际格式**算：每字形定长 16px。

    ## 为什么要有两个宽度函数

    `text_px()` 假设 ASCII 半宽 8px，八份页面文档的「184px / 232px
    （余 48px）」全部基于它。但 `assets/font16.bin` 实测是
    **定长 per=32（16×16 的 1bpp），头部没有任何 advance / 变宽字段**：

        magic=FNT1 ver=1 字号=16 per=32 字形数=550

    ASCII 字形的墨迹确实只占中间几列（「A」x=2~11、「5」x=4~11、
    「[」x=6~9），是半宽画在全宽格里居中 —— 所以半宽渲染在数据上可行，
    但需要渲染器按字符类型决定步进，而字库格式不带这个信息。

    差距不小：P1 提示行「[A]照料  [B]图鉴  [C]遭遇」
    半宽模型 200px（放得下），定长模型 **304px（溢出 72px）**。

    ## 没有替 text_px 定论，因为这是规格决策

    三条路都成立，选哪条要看固件渲染器怎么写：
      ① 渲染器按 `c < 0x80` 用 8px 步进 —— 零字库改动，但要在固件里
         硬编码「ASCII 半宽」这条规则，且 550 个字形里有 13 个白占一半格
      ② 字库加 advance 字段（每字形 +1 B，共 +550 B）—— 格式变更，
         但把宽度信息放在数据里，渲染器不需要知道字符分类
      ③ 提示行改用更短的文案 —— 不动格式，但八页都要改，且
         `KEY_HINT_MAX_ACTION = 2` 已经压到极限

    在定下来之前，`check_key_hints()` 同时按两个模型校验，
    并把差距报出来 —— 让这个矛盾在跑校验时可见，而不是留到真机上发现截断。
    """
    return GLYPH * len(s)


def check_key_hints() -> tuple[list[str], list[str]]:
    """三键提示是否放得下 —— 动作词 ≤2 字，且整行放得下。

    返回 (fails, warns)。按**两个**宽度模型校验：text_px（半宽假设，
    页面文档用的）与 text_px_fixed（字库实际的定长）。

    **后者超宽只是 warns，不算 fails** —— 它是已知的规格待决项
    （见 text_px_fixed 的说明），不是文案的错。而且渲染器实际按
    「字符类型决定步进」（render.c，真机验过：ASCII 8px 步进只切
    右侧空白），定长模型是**已经放弃的假设**，拿它当失败判据会让
    文档生成在干净树上也挂掉（发生过：gen_pages 因此一直 exit 1，
    docs/pages 停更，P2 文档落后于 KEYS 的键位改动）。

    真失败只有两种：动作词 >2 字、text_px 超宽 —— 这些仍会让
    gen_pages 拒绝生成。
    """
    bad, warns = [], []
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
        # 字库实际格式下的宽度 —— 规格待决，只提示不判失败
        pxf = text_px_fixed(line)
        if pxf > budget:
            warns.append(f"⚠️ {page} 按字库定长 16px/字算 {pxf}px > "
                         f"{budget}px（溢出 {pxf - budget}px）—— 半宽模型算"
                         f" {px}px。font16.bin 无 advance 字段，见 "
                         f"text_px_fixed()（渲染器已按字符类型步进，"
                         f"此模型仅记录格式事实）")
    return bad, warns


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


# ---------------------------------------------------------------------------
# 可变宽元素登记表（D54，第二十四派活）
#
# ## 为什么需要它 —— check_line_widths() 正确地回答了一个不同的问题
#
# `check_line_widths()` 遍历 PAGES 里的**固定模板字**，判据是 `px > USABLE_W`
# （232px = 整屏可用宽）。它报绿，而真溢出可以存在，因为两个盲区：
#
#   盲区①  不代入数据池。PAGES['P3'] 的 keys 是
#          ['eff','result','labels','fled','weakened'] —— **没有「{name} Lv{level}」**。
#          那个模板在固件 snprintf 里，Python 侧根本不知道它存在。
#   盲区②  预算恒为整屏宽，不看元素起始 x。P3 主宠名牌从 x=112 起，
#          真实预算是 232-112=120，而判据拿 232 去比：
#          「三合一磁怪 Lv100」128px ≤ 232 → 判通过。
#
# **这比「没有约束层」更危险：一个报绿的门禁让所有人以为这件事有人管着。**
# 所以下面这张表登记的是「模板 + 数据池 + 该元素的真实容器」三者的组合。
#
# ## 最坏输入必须现算，不能手抄
#
# 本文件上方曾有注释写「招式名最长 5 字（百万吨重拳）」——
# **实测 5 字招式有 4 个**（百万吨重拳/百万吨重踢/尖刺加农炮/骨头回力镖）。
# 手抄的最坏输入会腐烂，这是现成证据。所以最坏样本一律从
# gen1.bin / moves.bin 现算（见 _pool()），将来接 gen2 的 251 只判据自动跟着变。
#
# ## 字段语义
#   page/elem  定位用；src 指向固件真实调用点
#   x          左锚元素的起始 x；右对齐元素填 None（预算算法不同）
#   right      右界。左锚元素可用宽 = right - x；右对齐 = right - MARGIN
#   tmpl       固件 snprintf 的格式，占位符处代入最坏数据
#   fallback   固件自带的降级分支（有则参与判定 —— 判据要测「最终上屏的东西」，
#              不是「第一版拼装结果」）
# ---------------------------------------------------------------------------

_POOL_CACHE: dict | None = None


def _pool() -> dict:
    """物种名 / 招式名的最坏样本 —— 从 assets/*.bin 现算。

    复用 tools/pipeline/inventory_assets.py 的 parse_gen1 / parse_moves：
    它们已做 magic + 记录数 + 池长度断言（两个文件头都是 16 字节，
    Hub 与 test 先后在这上面栽过）。**不要在这里再写第三份解析器。**
    """
    global _POOL_CACHE
    if _POOL_CACHE is not None:
        return _POOL_CACHE
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    pipeline = os.path.join(repo, "tools", "pipeline")
    if pipeline not in sys.path:
        sys.path.insert(0, pipeline)
    import inventory_assets as _IA          # noqa: E402

    g = _IA.parse_gen1(os.path.join(repo, "assets", "gen1.bin"))
    mv = _IA.parse_moves(os.path.join(repo, "assets", "moves.bin"))
    species = [m["zh"] for m in g["mons"]]
    moves = [m["zh"] for m in mv["moves"]]
    if not species or not moves:
        raise RuntimeError("gen1.bin / moves.bin 解析出空池 —— 判据会假绿，拒绝继续")
    _POOL_CACHE = {
        "species": max(species, key=text_px),
        "species_all": species,
        "move": max(moves, key=text_px),
        "moves_all": moves,
        "level": "100",     # 等级/百分比/数量取位数最多的字面量
        "pct": "100",
        "count": "99",
    }
    return _POOL_CACHE


def _fill(tmpl: str, pool: dict) -> str:
    """登记表模板的占位符换成最坏数据。"""
    return (tmpl.replace("{species}", pool["species"])
                .replace("{move}", pool["move"])
                .replace("{level}", pool["level"])
                .replace("{pct}", pool["pct"])
                .replace("{count}", pool["count"]))


# (page, elem, x, right, tmpl, fallback_tmpl|None, src)
VAR_ELEMENTS: list[tuple] = [
    ("P3", "主宠名牌", 112, 232, "{species} Lv{level}", "{species}Lv{level}",
     "play_battle.c:230-237"),
    ("P3", "野怪名牌", None, 232, "{species} Lv{level}", None,
     "play_battle.c:153-158"),
    ("P3", "回合文字", 8, 232, "使用了{move}！", None, "play_battle.c:272"),
    ("P3", "回合首行", 8, 232, "野生{species}", None, "play_battle.c:262-275"),
    ("P3", "伤害数", None, 232, "-999 HP", None, "play_battle.c:277-279"),
    ("P3", "经验行", 8, 96, "经验 +99999", None,
     "play_battle.c:283-285"),   # 右侧 x96 起有「看起来虚弱了」，故右界 96
    ("P1", "名牌", 8, 232, "{species} Lv{level}", None, "play_idle.c:143-148"),
    ("P1", "亲密度", None, 232, "{pct}", None, "play_idle.c:153-155"),
    ("P1", "待处理数", 8, 232, "{count}", None,
     "play_idle.c:234-236"),     # hx+4，hx 由心形位置推；宽 ≤2 字符恒安全
    ("P2", "物种名", 18, 200, "{species}", None,
     "play_enc.c:158-164"),      # :166 注释自陈右界 200（稀有度星右对齐到 200）
    ("P2", "队列计数", None, 232, "{count}", None, "play_enc.c:128-131"),
    ("P2", "稀有度星", None, 232, "★★★★★", None,
     "play_enc.c:80-88"),        # 恒 5 个字形，helper 右对齐到 200
    ("P4", "物种名", None, 232, "{species}", None, "play_capture.c:151-154"),
    ("P4", "球名×数", 40, 232, "高级球 ×{count}", None, "play_capture.c:195-197"),
    ("P5", "物种名", 8, 232, "{species}", None, "play_care.c:120-121"),
    ("P5", "等级", None, 232, "等级 {level}", None, "play_care.c:117-118"),
    ("P5", "亲密度", None, 232, "亲密度 {pct}", None, "play_care.c:123-124"),
    ("P5", "轴数值", None, 232, "{pct}", None, "play_care.c:163-166"),
    ("P6", "格内编号", None, 232, "{count}", None, "play_dex.c:99-101"),
    ("P6", "已捕获数", None, 232, "151/151", None, "play_dex.c:67-69"),
    ("P6", "页码", None, 232, "99/99", None, "play_dex.c:105-107"),
    ("P0", "框号", None, 232, "7/7", None, "play_opening.c:149-151"),
    ("P0", "正文行", MARGIN, 232, "{species}使用了{move}！", None,
     "play_opening.c:186-188"),  # 打字机逐字显示，最坏是整行显完
]


def check_element_widths() -> list[str]:
    """可变宽元素在**各自容器**里放不放得下（模板 + 数据池最坏组合）。

    与 check_line_widths() 的分工：那个问「固定文案放得下整屏宽吗」，
    这个问「模板代入最坏数据后放得下该元素的容器吗」。两者都要跑。
    """
    pool = _pool()
    bad = []
    for page, elem, x, right, tmpl, fb, src in VAR_ELEMENTS:
        s = _fill(tmpl, pool)
        px = text_px(s)
        budget = (right - x) if x is not None else (right - MARGIN)
        used, note = s, ""
        if px > budget and fb:
            used = _fill(fb, pool)      # 固件自带降级 —— 判据测最终上屏的东西
            px = text_px(used)
            note = "（经固件回退分支）"
        if px > budget:
            bad.append(f"{page}.{elem} 「{used}」{px}px > {budget}px"
                       f"（x={x} 右界={right}）{note} @ {src}")
    return bad


def check_unregistered_elements() -> list[str]:
    """扫固件：`render_text(..., buf, ...)` 却没进 VAR_ELEMENTS 的，报红。

    ## 为什么漏登记本身必须红
    上面那张表是人手维护的。**没有这一条，表会慢慢过期而没人发现** ——
    新加一个 snprintf+render_text 的元素，判据默默不覆盖它，
    门禁照常绿。这与本轮修的 check_line_widths() 是同一个病：
    **一个报绿的门禁让所有人以为这件事有人管着。**

    判据取「render_text 的实参是运行时拼装的 buf」而非字面量 ——
    字面量已由 check_line_widths() 覆盖，且它们不随数据变。

    ## 已知弱点：登记窗口可重叠
    匹配用的是行号窗口（`lo-6 <= 调用行 <= hi+2`，容纳 snprintf 与
    render_text 分行）。**相邻登记项的窗口可能互相覆盖** ——
    实测摘掉「P3 回合文字（:272）」后仍不报，因为它的 render_text 在 :275，
    而「P3 回合首行」登记的 262-275 把那一行也盖住了。
    摘掉窗口不重叠的项（play_care.c:163-166 等）能正常报红。
    **所以这条守卫能挡「新增一个没人登记的元素」，
    但挡不住「删掉一条恰好被邻项窗口覆盖的登记」。** 后者要靠 review。
    """
    import os
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    main = os.path.join(os.path.dirname(here), "firmware", "main")
    if not os.path.isdir(main):
        return ["firmware/main 不存在 —— 无法做反向检查（宁可报红也不假绿）"]

    registered = {src.split("@")[-1].strip() for src in
                  (e[6] for e in VAR_ELEMENTS)}
    reg_files = {}
    for r in registered:                       # "play_battle.c:230-237"
        f, _, span = r.partition(":")
        lo = int(span.split("-")[0])
        hi = int(span.split("-")[1]) if "-" in span else lo
        reg_files.setdefault(f, []).append((lo, hi))

    call = re.compile(r"render_text\s*\(")
    bad = []
    for fn in sorted(os.listdir(main)):
        if not fn.startswith("play_") or not fn.endswith(".c"):
            continue
        lines = open(os.path.join(main, fn), encoding="utf-8").read().split("\n")
        for i, ln in enumerate(lines, 1):
            if not call.search(ln):
                continue
            # 实参可能跨行：从 render_text( 起截到配平的右括号为止，
            # **只看这一个调用的实参**。早期版本简单拼下一行，
            # 结果把下一条 render_text("字面量") 的内容也算进来，
            # 误报了 play_battle.c:282 与 play_dex.c:67 两处字面量调用。
            seg, depth, started = "", 0, False
            for j in range(i - 1, min(i + 2, len(lines))):
                for ch in lines[j]:
                    if ch == "(":
                        depth += 1
                        started = True
                    if started:
                        seg += ch
                    if ch == ")":
                        depth -= 1
                        if started and depth == 0:
                            break
                if started and depth == 0:
                    break
            if not re.search(r"[,(]\s*buf\s*[,)]", seg):
                continue               # 字面量/常量数组 —— 由 check_line_widths 管
            spans = reg_files.get(fn, [])
            if not any(lo - 6 <= i <= hi + 2 for lo, hi in spans):
                bad.append(f"{fn}:{i} render_text(buf) 未登记进 VAR_ELEMENTS："
                           f"「{ln.strip()[:60]}」")
    return bad


def audit() -> dict:
    """全量排版审计 —— CI 与验收平台都跑这个。"""
    kf, kw = check_key_hints()
    lb = check_line_widths()
    eb = check_element_widths()          # D54：模板+数据池 vs 元素容器
    ur = check_unregistered_elements()   # D54：漏登记本身要红
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
        "key_violations": kf,
        # ⚠️ 提示单独放 —— 调用方（gen_pages）应打印但不因此拒生成
        "key_warnings": kw,
        "line_violations": lb,
        "element_violations": eb,
        "unregistered_elements": ur,
        "ok": not kf and not lb and not eb and not ur,
    }
