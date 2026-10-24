export const FIELDWORK_GUIDE = {
  "status": "released",
  "version": "2026.10.24 · 城都伙伴协作调查",
  "sourceHashes": {
    "firmware/main/johto_routes.c": "ad6da8d770794a41f055ee07e33263ced5d1bda2f5ae624ecb5134bf141f02f8",
    "firmware/main/johto_routes.h": "db0bf2ee3999e12f370ef0d873199d987f7b4ef261e599801c7952347638eee9",
    "firmware/main/johto.c": "d595a38d8df3cdf27f7ec265fa8403d3f976eedc5c00ba8269ec8694ef863ba2",
    "firmware/main/johto_story.c": "e6083a83ab46d40b238a1f68515387855b7a92732846c7e4e48e189df6e1f3d9",
    "assets/gen1.bin": "4eb0acf61b227ace9f66b9324099d0ca610ea684ff0a969ead05b84247ed7508"
  },
  "sites": [
    {
      "id": 0,
      "legend": 0,
      "step": 1,
      "title": "焦木间的电光",
      "clues": [
        "烧焦木柱还闪着微光。",
        "靠近时，毛发微微竖起。"
      ],
      "hints": [
        "能储存电的伙伴可以回应。",
        "试着让微光连成一道电流。"
      ],
      "routeId": 4,
      "pathId": 0,
      "route": "烧焦塔",
      "path": "焦木长廊",
      "badges": 4,
      "types": [
        "电"
      ],
      "examples": [
        {
          "id": 181,
          "name": "电龙",
          "routeId": 4,
          "pathId": 0,
          "location": "烧焦塔 · 焦木长廊"
        },
        {
          "id": 172,
          "name": "皮丘",
          "routeId": 0,
          "pathId": 2,
          "location": "若叶郊野 · 池塘岸边"
        }
      ],
      "found": "雷击痕迹指向满金原野。",
      "next": "到牧场围栏寻找地面的变化。"
    },
    {
      "id": 1,
      "legend": 0,
      "step": 2,
      "title": "围栏下的震动",
      "clues": [
        "围栏下留下深深的脚印。",
        "泥土里传来细小的震动。"
      ],
      "hints": [
        "请熟悉泥土的伙伴听一听。",
        "震动藏在脚下，不在风中。"
      ],
      "routeId": 2,
      "pathId": 1,
      "route": "满金原野",
      "path": "牧场围栏",
      "badges": 4,
      "types": [
        "地面"
      ],
      "examples": [
        {
          "id": 194,
          "name": "乌波",
          "routeId": 0,
          "pathId": 2,
          "location": "若叶郊野 · 池塘岸边"
        },
        {
          "id": 231,
          "name": "小小象",
          "routeId": 2,
          "pathId": 2,
          "location": "满金原野 · 河岸草地"
        }
      ],
      "found": "足迹正向冰雪之径延伸。",
      "next": "岩壁洞穴似乎留住了回声。"
    },
    {
      "id": 2,
      "legend": 0,
      "step": 3,
      "title": "岩壁里的回声",
      "clues": [
        "雪中的脚印在石壁前消失。",
        "洞穴深处传来低沉回声。"
      ],
      "hints": [
        "找能感知岩土回声的伙伴。",
        "轻叩石壁，也许会有回应。"
      ],
      "routeId": 5,
      "pathId": 2,
      "route": "冰雪之径",
      "path": "岩壁洞穴",
      "badges": 5,
      "types": [
        "地面",
        "岩石"
      ],
      "examples": [
        {
          "id": 246,
          "name": "幼基拉斯",
          "routeId": 5,
          "pathId": 2,
          "location": "冰雪之径 · 岩壁洞穴"
        },
        {
          "id": 247,
          "name": "沙基拉斯",
          "routeId": 5,
          "pathId": 2,
          "location": "冰雪之径 · 岩壁洞穴"
        }
      ],
      "found": "三处痕迹连成了雷鸣的方向。",
      "next": "回到调查册，接近雷鸣。"
    },
    {
      "id": 3,
      "legend": 1,
      "step": 1,
      "title": "余烬仍然温热",
      "clues": [
        "木炭早已冷却。",
        "只有深处的灰烬还温热。"
      ],
      "hints": [
        "不怕火焰的伙伴更能靠近。",
        "余温需要另一团火来唤醒。"
      ],
      "routeId": 4,
      "pathId": 2,
      "route": "烧焦塔",
      "path": "余烬深处",
      "badges": 4,
      "types": [
        "火"
      ],
      "examples": [
        {
          "id": 218,
          "name": "熔岩虫",
          "routeId": 4,
          "pathId": 2,
          "location": "烧焦塔 · 余烬深处"
        },
        {
          "id": 228,
          "name": "戴鲁比",
          "routeId": 4,
          "pathId": 2,
          "location": "烧焦塔 · 余烬深处"
        }
      ],
      "found": "温热的足迹延伸向桧皮林地。",
      "next": "到密林深处寻找暖风。"
    },
    {
      "id": 4,
      "legend": 1,
      "step": 2,
      "title": "密林中的暖风",
      "clues": [
        "越往深处，草叶越干燥。",
        "无风时也有热气拂过。"
      ],
      "hints": [
        "熟悉火焰的伙伴能辨别。",
        "热气散去前，循着余温找。"
      ],
      "routeId": 1,
      "pathId": 2,
      "route": "桧皮林地",
      "path": "密林深处",
      "badges": 4,
      "types": [
        "火"
      ],
      "examples": [
        {
          "id": 218,
          "name": "熔岩虫",
          "routeId": 4,
          "pathId": 2,
          "location": "烧焦塔 · 余烬深处"
        },
        {
          "id": 228,
          "name": "戴鲁比",
          "routeId": 4,
          "pathId": 2,
          "location": "烧焦塔 · 余烬深处"
        }
      ],
      "found": "足迹越过林地，通向铃铛塔。",
      "next": "先取得通往古塔的徽章。"
    },
    {
      "id": 5,
      "legend": 1,
      "step": 3,
      "title": "庭院里的余温",
      "clues": [
        "庭院石阶上落着一圈灰。",
        "靠近花草的石面仍然温热。"
      ],
      "hints": [
        "让能唤起火焰的伙伴试试。",
        "石阶似乎在等待火星回应。"
      ],
      "routeId": 7,
      "pathId": 0,
      "route": "铃铛塔",
      "path": "古塔庭院",
      "badges": 7,
      "types": [
        "火"
      ],
      "examples": [
        {
          "id": 157,
          "name": "火暴兽",
          "routeId": 7,
          "pathId": 0,
          "location": "铃铛塔 · 古塔庭院"
        },
        {
          "id": 218,
          "name": "熔岩虫",
          "routeId": 4,
          "pathId": 2,
          "location": "烧焦塔 · 余烬深处"
        }
      ],
      "found": "三处余温指向同一道身影。",
      "next": "回到调查册，循着焦痕靠近。"
    },
    {
      "id": 6,
      "legend": 2,
      "step": 1,
      "title": "逆流而行的波纹",
      "clues": [
        "河岸的草叶被水打湿。",
        "一道清澈波纹正向上游移动。"
      ],
      "hints": [
        "熟悉水流的伙伴能跟上它。",
        "波纹逆流而行，并非风吹。"
      ],
      "routeId": 2,
      "pathId": 2,
      "route": "满金原野",
      "path": "河岸草地",
      "badges": 4,
      "types": [
        "水"
      ],
      "examples": [
        {
          "id": 183,
          "name": "玛力露",
          "routeId": 2,
          "pathId": 2,
          "location": "满金原野 · 河岸草地"
        },
        {
          "id": 184,
          "name": "玛力露丽",
          "routeId": 2,
          "pathId": 2,
          "location": "满金原野 · 河岸草地"
        }
      ],
      "found": "清澈的水流通向漩涡列岛。",
      "next": "先取得前往列岛的徽章。"
    },
    {
      "id": 7,
      "legend": 2,
      "step": 2,
      "title": "浅滩里的清泉",
      "clues": [
        "潮水退后，水草仍在摇动。",
        "清泉被缠绕的根须挡住了。"
      ],
      "hints": [
        "请亲近水或草木的伙伴。",
        "泉眼或许就在根须之间。"
      ],
      "routeId": 6,
      "pathId": 0,
      "route": "漩涡列岛",
      "path": "浅滩水草",
      "badges": 6,
      "types": [
        "水",
        "草"
      ],
      "examples": [
        {
          "id": 158,
          "name": "小锯鳄",
          "routeId": 6,
          "pathId": 0,
          "location": "漩涡列岛 · 浅滩水草"
        },
        {
          "id": 191,
          "name": "向日种子",
          "routeId": 0,
          "pathId": 0,
          "location": "若叶郊野 · 草丛小路"
        }
      ],
      "found": "水流受阻的原因已经清楚了。",
      "next": "前往调查册，完成净水试炼。"
    },
    {
      "id": 8,
      "legend": 3,
      "step": 1,
      "title": "银羽映出的潮线",
      "clues": [
        "银色之羽映着细细的潮线。",
        "浅滩水草朝着同一方向摆动。"
      ],
      "hints": [
        "熟悉潮水的伙伴能辨方向。",
        "顺着水草，留意银羽的变化。"
      ],
      "routeId": 6,
      "pathId": 0,
      "route": "漩涡列岛",
      "path": "浅滩水草",
      "badges": 6,
      "types": [
        "水"
      ],
      "examples": [
        {
          "id": 158,
          "name": "小锯鳄",
          "routeId": 6,
          "pathId": 0,
          "location": "漩涡列岛 · 浅滩水草"
        },
        {
          "id": 184,
          "name": "玛力露丽",
          "routeId": 6,
          "pathId": 0,
          "location": "漩涡列岛 · 浅滩水草"
        }
      ],
      "found": "第一道潮线通向珊瑚海湾。",
      "next": "那里有一串忽明忽暗的光点。"
    },
    {
      "id": 9,
      "legend": 3,
      "step": 2,
      "title": "珊瑚间的光点",
      "clues": [
        "珊瑚间的光点有节奏地闪着。",
        "像在等待另一束光回应。"
      ],
      "hints": [
        "让能放出电光的伙伴回应。",
        "光点正在等待相同的节奏。"
      ],
      "routeId": 6,
      "pathId": 1,
      "route": "漩涡列岛",
      "path": "珊瑚海湾",
      "badges": 6,
      "types": [
        "电"
      ],
      "examples": [
        {
          "id": 170,
          "name": "灯笼鱼",
          "routeId": 6,
          "pathId": 1,
          "location": "漩涡列岛 · 珊瑚海湾"
        },
        {
          "id": 172,
          "name": "皮丘",
          "routeId": 0,
          "pathId": 2,
          "location": "若叶郊野 · 池塘岸边"
        }
      ],
      "found": "第二道潮线指向潮汐深处。",
      "next": "找能适应海浪的伙伴同行。"
    },
    {
      "id": 10,
      "legend": 3,
      "step": 3,
      "title": "风与潮交汇处",
      "clues": [
        "最深处的海浪突然分开。",
        "海风正托起那枚银色之羽。"
      ],
      "hints": [
        "会乘风或游水的伙伴能靠近。",
        "海浪与高风，任一条都可通。"
      ],
      "routeId": 6,
      "pathId": 2,
      "route": "漩涡列岛",
      "path": "潮汐深处",
      "badges": 6,
      "types": [
        "水",
        "飞行"
      ],
      "examples": [
        {
          "id": 226,
          "name": "巨翅飞鱼",
          "routeId": 6,
          "pathId": 2,
          "location": "漩涡列岛 · 潮汐深处"
        },
        {
          "id": 171,
          "name": "电灯怪",
          "routeId": 6,
          "pathId": 2,
          "location": "漩涡列岛 · 潮汐深处"
        }
      ],
      "found": "三道潮线交汇在海渊之上。",
      "next": "回到调查册，回应海的呼唤。"
    },
    {
      "id": 11,
      "legend": 4,
      "step": 1,
      "title": "壁画上的晨光",
      "clues": [
        "庭院壁画上的日轮暗了。",
        "三道身影围着一处火焰刻纹。"
      ],
      "hints": [
        "让能唤起火焰的伙伴照亮。",
        "刻纹还缺一束温暖的光。"
      ],
      "routeId": 7,
      "pathId": 0,
      "route": "铃铛塔",
      "path": "古塔庭院",
      "badges": 7,
      "types": [
        "火"
      ],
      "examples": [
        {
          "id": 157,
          "name": "火暴兽",
          "routeId": 7,
          "pathId": 0,
          "location": "铃铛塔 · 古塔庭院"
        },
        {
          "id": 218,
          "name": "熔岩虫",
          "routeId": 4,
          "pathId": 2,
          "location": "烧焦塔 · 余烬深处"
        }
      ],
      "found": "日轮旁显出月亮的符号。",
      "next": "去月光长廊读懂新的刻纹。"
    },
    {
      "id": 12,
      "legend": 4,
      "step": 2,
      "title": "月下无声的铃",
      "clues": [
        "长廊里的铃铛没有摆动。",
        "墙上的影子却轻轻摇晃。"
      ],
      "hints": [
        "请能感知无形力量的伙伴。",
        "铃声藏在眼睛看不见的地方。"
      ],
      "routeId": 7,
      "pathId": 1,
      "route": "铃铛塔",
      "path": "月光长廊",
      "badges": 7,
      "types": [
        "超能",
        "幽灵"
      ],
      "examples": [
        {
          "id": 199,
          "name": "呆呆王",
          "routeId": 7,
          "pathId": 1,
          "location": "铃铛塔 · 月光长廊"
        },
        {
          "id": 200,
          "name": "梦妖",
          "routeId": 3,
          "pathId": 0,
          "location": "缘朱遗迹 · 古木阴影"
        }
      ],
      "found": "月影在墙上指向塔顶。",
      "next": "带能乘风的伙伴登上回廊。"
    },
    {
      "id": 13,
      "legend": 4,
      "step": 3,
      "title": "塔顶的虹光",
      "clues": [
        "塔顶的铃声被风带得很远。",
        "一束虹光停在高处的檐角。"
      ],
      "hints": [
        "会乘风的伙伴或许能靠近。",
        "虹光在高处，沿风寻找入口。"
      ],
      "routeId": 7,
      "pathId": 2,
      "route": "铃铛塔",
      "path": "塔顶回廊",
      "badges": 7,
      "types": [
        "飞行"
      ],
      "examples": [
        {
          "id": 227,
          "name": "盔甲鸟",
          "routeId": 7,
          "pathId": 2,
          "location": "铃铛塔 · 塔顶回廊"
        },
        {
          "id": 165,
          "name": "芭瓢虫",
          "routeId": 0,
          "pathId": 0,
          "location": "若叶郊野 · 草丛小路"
        }
      ],
      "found": "壁画与三兽的记录相互呼应。",
      "next": "回到调查册，迎接虹光主人。"
    },
    {
      "id": 14,
      "legend": 5,
      "step": 1,
      "title": "古树的两圈年轮",
      "clues": [
        "树干的两圈年轮重叠在一起。",
        "嫩芽回应着关都森林的气息。"
      ],
      "hints": [
        "熟悉草木的伙伴能听见它。",
        "两圈年轮在等同一个回应。"
      ],
      "routeId": 1,
      "pathId": 0,
      "route": "桧皮林地",
      "path": "树干调查",
      "badges": 4,
      "types": [
        "草"
      ],
      "examples": [
        {
          "id": 191,
          "name": "向日种子",
          "routeId": 0,
          "pathId": 0,
          "location": "若叶郊野 · 草丛小路"
        },
        {
          "id": 187,
          "name": "毽子草",
          "routeId": 0,
          "pathId": 1,
          "location": "若叶郊野 · 林间树梢"
        }
      ],
      "found": "回声从古树传入密林深处。",
      "next": "寻找影子与树木错开的地方。"
    },
    {
      "id": 15,
      "legend": 5,
      "step": 2,
      "title": "迟到了一步的影子",
      "clues": [
        "密林中的树影慢了一步。",
        "脚步停止，影子才慢慢停下。"
      ],
      "hints": [
        "请能感知无形力量的伙伴。",
        "影子似乎落在了另一个时刻。"
      ],
      "routeId": 1,
      "pathId": 2,
      "route": "桧皮林地",
      "path": "密林深处",
      "badges": 4,
      "types": [
        "超能",
        "幽灵"
      ],
      "examples": [
        {
          "id": 177,
          "name": "天然雀",
          "routeId": 1,
          "pathId": 1,
          "location": "桧皮林地 · 林冠穿行"
        },
        {
          "id": 200,
          "name": "梦妖",
          "routeId": 3,
          "pathId": 0,
          "location": "缘朱遗迹 · 古木阴影"
        }
      ],
      "found": "两个时刻交汇在林冠之上。",
      "next": "带熟悉草木的伙伴靠近树梢。"
    },
    {
      "id": 16,
      "legend": 5,
      "step": 3,
      "title": "两个时刻的嫩芽",
      "clues": [
        "树梢同时长出新叶与旧叶。",
        "回声正从重叠的枝叶间传来。"
      ],
      "hints": [
        "让亲近草木的伙伴回应。",
        "新叶与旧叶正在等待共鸣。"
      ],
      "routeId": 1,
      "pathId": 1,
      "route": "桧皮林地",
      "path": "林冠穿行",
      "badges": 4,
      "types": [
        "草"
      ],
      "examples": [
        {
          "id": 187,
          "name": "毽子草",
          "routeId": 1,
          "pathId": 1,
          "location": "桧皮林地 · 林冠穿行"
        },
        {
          "id": 188,
          "name": "毽子花",
          "routeId": 1,
          "pathId": 1,
          "location": "桧皮林地 · 林冠穿行"
        }
      ],
      "found": "森林里的两个时刻终于重合。",
      "next": "回到调查册，寻找回声主人。"
    }
  ]
};
