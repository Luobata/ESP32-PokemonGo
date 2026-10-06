# 官网部署完成 · 2026-10-06

- 官网：<https://luobata.github.io/ESP32-PokemonGo/guide/>
- 存档与升级入口：<https://luobata.github.io/ESP32-PokemonGo/>
- devbox：<http://10.37.197.13:8767/guide/>
- 网站 PR：<https://github.com/Luobata/ESP32-PokemonGo/pull/2>，已合并。
- 当前 main 网站提交：`31f7960a06a4ba3000ecdc3bff6ca76eb5bfbdc7`。
- Pages CI：<https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37451853559>，成功。
- PR 完整固件/存档 CI：<https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37450816362>，成功。

线上核验 Pages 与 devbox 各 10 个网页资源及离线 ZIP，共 22 个响应，与本地源码逐字节相同；明细见 `reports/evidence/game-guide-2026-10-06/deployment.json`。

离线 ZIP SHA-256：`cfc1cffa5ef7bc6f5156632f33763f41de3f4771df2a1cf09f16e4543a272fec`。

实际浏览器验证官网首页图片加载正常、无控制台错误，官网 → 存档管理 → 官网双向入口可用。公开首页截图见 `reports/evidence/game-guide-2026-10-06/published-home.png`。

线上刷新即可；已下载的离线工具需重新下载 ZIP 才带有手册。本次未更改 USB 导入协议。已发布固件规则与开发体验规则分开展示；V5–V18 与 V5–V20 的兼容范围分别对应各自固件，阅读网站不需要重烧设备。

轮换访客、特殊发现和养成增强已推送到 `codex/exploration-balance-chain`，最终游戏源码 `2e37c676bace83c822ea67802cae7845bf405103`。main 此次仅更新网站及分发/验证工具；没有上传新的固件包、社区版本或烧录设备。完整游戏构建身份与本地存档回归详见 `reports/exploration-visitors-care-2026-10-06.md`。
