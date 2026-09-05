// main/dbg.h —— 串口注入按键。见 dbg.c 顶部的理由。
#pragma once

// 起一个任务读 stdin。a/b/c 单击，A/B/C 双击，s 截图。
void dbg_start(void);
