// wifi-collect — macOS WiFi 环境采集器
//
// 输出 NDJSON，每行一次扫描，格式见 docs/06-engineering.md#数据格式
// 供 sim/replay.py 与 sim/prototype.py 回放。
//
// 构建：./build.sh
// 用法：./wifi-collect --interval 30 --out data/raw/today.ndjson

import CoreWLAN
import CoreLocation
import Foundation

// MARK: - 参数

struct Options {
    var interval: Double = 30      // 扫描间隔（秒）
    var out: String? = nil         // 输出路径，nil = stdout
    var count: Int = 0             // 扫描次数，0 = 无限
    var quiet = false              // 不打印进度到 stderr
    var allowDegraded = false      // 无 BSSID 时也继续（降级模式）
}

func parseArgs() -> Options {
    var o = Options()
    var it = CommandLine.arguments.dropFirst().makeIterator()
    while let a = it.next() {
        switch a {
        case "--interval", "-i":
            if let v = it.next(), let d = Double(v), d > 0 { o.interval = d }
            else { fail("--interval 需要一个正数（秒）") }
        case "--out", "-o":
            guard let v = it.next() else { fail("--out 需要一个路径") }
            o.out = v
        case "--count", "-n":
            if let v = it.next(), let n = Int(v), n >= 0 { o.count = n }
            else { fail("--count 需要一个非负整数") }
        case "--quiet", "-q":     o.quiet = true
        case "--allow-degraded":  o.allowDegraded = true
        case "--help", "-h":      usage(); exit(0)
        default: fail("未知参数：\(a)（--help 查看用法）")
        }
    }
    return o
}

func usage() {
    print("""
    wifi-collect — 采集 WiFi 环境指纹，输出 NDJSON

    用法：
      wifi-collect [--interval 30] [--out FILE] [--count N] [--quiet]
                   [--allow-degraded]

      -i, --interval N    扫描间隔秒数（默认 30）
      -o, --out FILE      输出文件（默认 stdout）。以追加模式打开
      -n, --count N       扫描 N 次后退出（默认 0 = 无限，Ctrl-C 停止）
      -q, --quiet         不向 stderr 打印进度
          --allow-degraded  即使拿不到 BSSID 也继续采集（见下）

    定位授权：
      macOS 12+ 对 BSSID 有权限门禁。没有定位授权时 bssid/ssid 全为 nil，
      只剩 RSSI 和 channel —— 而指纹方案的核心正是 BSSID。
      本程序启动时会自我检测；若检测到无授权会给出指引并退出，
      除非显式传 --allow-degraded 用合成伪 BSSID 跑通管线（判别质量下降，
      不能用于最终标定）。详见 README.md。
    """)
}

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write("错误：\(msg)\n".data(using: .utf8)!)
    exit(2)
}

func note(_ msg: String) {
    FileHandle.standardError.write("\(msg)\n".data(using: .utf8)!)
}

// MARK: - 输出

/// 行缓冲写入器。每次扫描后 flush，保证 Ctrl-C 不丢数据。
final class LineWriter {
    private let fh: FileHandle
    private let isFile: Bool

    init(path: String?) {
        guard let path = path else {
            fh = FileHandle.standardOutput
            isFile = false
            return
        }
        let dir = (path as NSString).deletingLastPathComponent
        if !dir.isEmpty && !FileManager.default.fileExists(atPath: dir) {
            try? FileManager.default.createDirectory(
                atPath: dir, withIntermediateDirectories: true)
        }
        if !FileManager.default.fileExists(atPath: path) {
            FileManager.default.createFile(atPath: path, contents: nil)
        }
        guard let h = FileHandle(forWritingAtPath: path) else {
            fail("无法写入 \(path)")
        }
        h.seekToEndOfFile()   // 追加，不覆盖已有采集
        fh = h
        isFile = true
    }

    func write(_ line: String) {
        guard let d = (line + "\n").data(using: .utf8) else { return }
        fh.write(d)
    }

    func close() { if isFile { try? fh.close() } }
}

// MARK: - JSON 转义

func jsonString(_ s: String) -> String {
    var out = "\""
    for c in s.unicodeScalars {
        switch c {
        case "\"":  out += "\\\""
        case "\\":  out += "\\\\"
        case "\n":  out += "\\n"
        case "\r":  out += "\\r"
        case "\t":  out += "\\t"
        default:
            if c.value < 0x20 {
                out += String(format: "\\u%04x", c.value)
            } else {
                out.unicodeScalars.append(c)
            }
        }
    }
    return out + "\""
}

// MARK: - authmode 归一化

func authLabel(_ n: CWNetwork) -> String {
    // 从最强到最弱依次判定，取第一个命中的
    let checks: [(CWSecurity, String)] = [
        (.wpa3Enterprise, "wpa3-ent"), (.wpa3Personal, "wpa3"),
        (.wpa2Enterprise, "wpa2-ent"), (.wpa2Personal, "wpa2"),
        (.wpaEnterprise,  "wpa-ent"),  (.wpaPersonal,  "wpa"),
        (.WEP, "wep"), (.none, "open"),
    ]
    for (sec, label) in checks where n.supportsSecurity(sec) { return label }
    return "unknown"
}

// MARK: - 定位授权自检

/// CLLocationManager 的 delegate。
///
/// 授权状态变化是通过 delegate 回调送达的，而回调只在 run loop 转起来时才会派发。
/// 早期版本创建完 manager 就直接扫描、从不进 run loop，
/// 于是 authorizationStatus 永远停在 notDetermined —— 即便用户已经在
/// 系统设置里打开了开关。这是实测踩到的坑（status=0 但开关已开）。
final class AuthWaiter: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()
    private var settled = false

    override init() {
        super.init()
        manager.delegate = self
    }

    func locationManagerDidChangeAuthorization(_ m: CLLocationManager) {
        if m.authorizationStatus != .notDetermined { settled = true }
    }

    /// 请求授权并把 run loop 转起来，直到状态确定或超时。
    func waitForAuthorization(timeout: TimeInterval = 3.0) -> CLAuthorizationStatus {
        if manager.authorizationStatus != .notDetermined {
            return manager.authorizationStatus
        }

        manager.requestWhenInUseAuthorization()

        // 关键：转 run loop 让 delegate 回调有机会派发。
        // 弹窗也需要 run loop 才能显示。
        let deadline = Date().addingTimeInterval(timeout)
        while !settled && Date() < deadline {
            RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.1))
        }
        return manager.authorizationStatus
    }
}

/// 返回 true 表示能拿到真 BSSID
func probeBSSIDAccess(_ iface: CWInterface) -> Bool {
    // 先把授权谈妥（含 run loop），再验证实际能否读到 BSSID
    _ = AuthWaiter().waitForAuthorization()

    // 以实扫结果为准而非查 authorizationStatus ——
    // 最终能否读到 BSSID 由系统综合判定
    guard let nets = try? iface.scanForNetworks(withSSID: nil) else { return false }
    return nets.contains { $0.bssid != nil }
}

/// 无授权时的降级：用 channel + RSSI 分桶合成稳定的伪 BSSID。
/// 同一个物理 AP 在相邻扫描中通常落进同一个桶，因此仍能提供弱指纹。
/// 分桶宽度 6dB —— 太窄会因 RSSI 抖动裂成多个假 AP，太宽会把不同 AP 合并。
func syntheticBSSID(channel: Int, rssi: Int, index: Int) -> String {
    let bucket = (rssi / 6) * 6
    let h = UInt32(bitPattern: Int32(channel &* 7919 &+ bucket &* 104729 &+ index))
    let b = withUnsafeBytes(of: h.bigEndian) { Array($0) }
    return "syn:" + b.map { String(format: "%02x", $0) }.joined(separator: ":")
}

// MARK: - 主流程

let opts = parseArgs()

guard let iface = CWWiFiClient.shared().interface() else {
    fail("找不到 WiFi 接口。确认机器有 WiFi 且已开启。")
}

let hasBSSID = probeBSSIDAccess(iface)

if !hasBSSID {
    if !opts.allowDegraded {
        note("""
        ⚠️  拿不到 BSSID —— 缺少定位授权。

        macOS 12+ 要求定位授权才能读取 BSSID/SSID。这是指纹方案的核心字段，
        没有它采集的数据无法用于标定。

        TCC（隐私授权）按 bundle identifier 判定权限，而裸可执行文件没有身份 ——
        所以它既不会出现在「定位服务」列表里，sudo 也提不了权（已实测无效）。

        解决方式（详见 tools/collector/README.md）：

          1. 打包成 .app 让它有身份：
               ./make-app.sh
             然后在你自己的终端里跑一次触发授权弹窗（点「允许」）：
               ./WiFiCollect.app/Contents/MacOS/wifi-collect --count 1
             没弹窗就去 系统设置 → 隐私与安全性 → 定位服务，
             找到 WiFiCollect 打开开关（打包后它才会出现在列表里）。
             验证：./check-auth.sh --app

          2. 若只想先把管线跑通，加 --allow-degraded 用合成伪 BSSID
             （判别质量明显下降，仅用于验证代码逻辑）

        """)
        exit(1)
    }
    note("⚠️  降级模式：BSSID 不可用，使用合成伪 BSSID。数据仅供管线验证，不可用于标定。")
}

let writer = LineWriter(path: opts.out)

// Ctrl-C 干净退出：flush 并关闭文件
signal(SIGINT) { _ in
    FileHandle.standardError.write("\n采集结束。\n".data(using: .utf8)!)
    exit(0)
}

if !opts.quiet {
    let dst = opts.out ?? "stdout"
    let lim = opts.count == 0 ? "无限（Ctrl-C 停止）" : "\(opts.count) 次"
    note("开始采集 → \(dst)　间隔 \(Int(opts.interval))s　次数 \(lim)")
    if hasBSSID { note("BSSID 可用 ✓") }
}

var round = 0
while opts.count == 0 || round < opts.count {
    round += 1
    let ts = Int(Date().timeIntervalSince1970)

    var networks: [CWNetwork] = []
    do {
        networks = Array(try iface.scanForNetworks(withSSID: nil))
    } catch {
        // 扫描失败不该终止长跑采集 —— 记一行空结果，继续
        note("[\(round)] 扫描失败：\(error.localizedDescription)")
        writer.write("{\"ts\":\(ts),\"aps\":[],\"err\":\"scan_failed\"}")
        if opts.count == 0 || round < opts.count { Thread.sleep(forTimeInterval: opts.interval) }
        continue
    }

    var items: [String] = []
    for (i, n) in networks.enumerated() {
        let rssi = n.rssiValue
        let ch   = n.wlanChannel?.channelNumber ?? 0
        let bssid = n.bssid ?? syntheticBSSID(channel: ch, rssi: rssi, index: i)
        let ssid  = n.ssid ?? ""   // 隐藏 SSID 是空串，不是错误

        items.append("{\"b\":\(jsonString(bssid)),\"s\":\(jsonString(ssid))," +
                     "\"r\":\(rssi),\"c\":\(ch),\"a\":\(jsonString(authLabel(n)))}")
    }

    var line = "{\"ts\":\(ts),\"aps\":[\(items.joined(separator: ","))]"
    if !hasBSSID { line += ",\"degraded\":true" }
    line += "}"
    writer.write(line)

    if !opts.quiet {
        let g24 = networks.filter { ($0.wlanChannel?.channelNumber ?? 0) <= 14 }.count
        note("[\(round)] \(networks.count) 个 AP（2.4G: \(g24)）")
    }

    if opts.count == 0 || round < opts.count {
        Thread.sleep(forTimeInterval: opts.interval)
    }
}

writer.close()
if !opts.quiet { note("完成，共 \(round) 次扫描。") }
