# 实施与测试报告

本次交付独立维护的 x86_64 MiniUPnPd/LuCI 包，已安装到授权的 `192.168.114.210`。aarch64、360T7 实机和 GitHub Actions 按用户指示暂不实施；没有修改 PVE 宿主机或生产主路由。

## 基线与源码

测试机为 ImmortalWrt 23.05-SNAPSHOT `r27943-8193c67d6c`，x86/64，Linux 5.15.164、musl 1.2.4，fw4 `2023-09-01-598d9fbb`、nftables 1.0.8、libmnl 1.0.5、libnftnl 1.2.6。原始网络、软件包、nft 规则见 `baseline-*`；配置备份位于 VM `/root/upnp-baseline/config.tgz`。PassWall 原已关闭。

使用 ImmortalWrt 23.05.4 x86_64 SDK/GCC 12.3 构建，不升级运行系统、内核或基础防火墙库。`final-packages.txt` 与最初软件包清单比较：已有包版本全部保持不变。生产包新增 libcap-ng 0.8.3；Python/ip 工具用于测试，不是 daemon 的依赖。

MiniUPnP 固定在 `f8c4f4c3320820e615b281147b3043f66c195f17`，包含 2.3.11 后的已合并修复。四组本地补丁及 SHA256、SDK 与 feeds commit 记录在 `../sources.json`，调查取舍见 [upstream.md](upstream.md)。未合并 PR 只作参考，没有整体套用。

运行时编译选项为 nftables、IGDv2、IPv6、NAT-PMP、PCP、leasefile、portinuse、regex、vendorcfg 和现有管理 socket。没有 iptables/PF/ipfw、旧 PPP、额外监控 daemon 或 PCP PEER/SNAT 链。默认不进行 STUN 公网探测。

## 可重复验证

主测试入口为 `../scripts/run-vm-tests.sh`，在 VM 内空桥/macvlan/network namespace 上建立隔离 LAN、第二客户端及 WAN。实验桥没有物理端口；公网地址类别也在此隔离拓扑上测试。实际 TCP/UDP echo、规则、conntrack 与协议结果共同判定通过。

| 验证组 | 证据与覆盖范围 |
|---|---|
| 主回归，28 项 | `repeat/integration.json`：IGDv1 描述/SOAP/SSDP 兼容、IGDv2、NAT-PMP、PCP、IPv4/IPv6 TCP/UDP 实际收发、同端口/不同端口、查询/续期/删除/到期、权限/边界/冲突、实际 conntrack、fw4 reload、stop/start、缺址/恢复及重复事件 |
| 生命周期，8 项 | `repeat/lifecycle.json`：同名 WAN 新 ifindex、仅 link-local 的 WAN6 路由、UCI 总开关/协议开关/IPv6 开关、禁用 secure_mode 后的非法目标拒绝、LAN IPv6 前缀淘汰 |
| 扩展，9 项 | `repeat/extended.json`：PCP nonce 跨恢复保留、WAN6 ULA 前缀变化后实际转发、RemoteHost 限制、续期保持其他 IPv6 ID、长 IPv6 租约行恢复/续期/删除、多客户端并发、真实 NAT-PMP 和 PCP 到期、反复缺址无日志洪泛 |
| 负载与空闲 | `repeat/soak.json` / `.stdout`：两个客户端 320 次双栈 TCP/UDP PCP 创建/删除；随后 300 秒空闲，前半无 WAN IPv4、后半双栈，记录 RSS/CPU/FD/规则/PID/日志 |
| 系统冷启动（旧持久路径配置） | `reboot-final.txt`：boot ID 改变、procd 自动运行、有效 IPv4 租约和 IPv6 ID 1234 恢复；测试目标仅在空虚拟 LAN 上，不向真实 LAN 添加映射 |
| 上游测试 | `upstream-tests-final.log`：权限解析、接口地址、SSDP 报文生成、HTTP GET/1 MiB POST/超限 header 拒绝；使用相同源码和补丁交叉编译，在 VM 执行 |
| LuCI 浏览器 | `luci-browser.json` / `luci.png`：真实 Chromium 页面、双栈列表、删除对应实际规则、删除保留 PID、总开关保存并应用、JavaScript 错误采集 |
| 构建与脚本 | `rebuild.log`、`reproducible-build.txt`、`shellcheck.txt`：最终 IPK 重复构建 SHA256 一致，补丁可应用，Python 语法检查、ShellCheck dash 检查通过 |

WAN IPv4 类别覆盖公网、RFC1918、CGNAT、benchmark 单播；IPv6 使用 ULA 的真实跨前缀路由，额外覆盖 WAN link-local 路由。短断线 1 秒、较长断线 6 秒以及恢复上限 5 秒已验证；这些时间不能替代小时级断线或多天运行证明。无 IPv4 时 IPv6 继续实际转发，反向也单独检查。

## 测试发现与修复

- 上游 nft IPv6 规则解析受 counter 表达式覆盖、Pinhole 缺失查询返回成功；修正后实际 IPv6 转发、计数和缺失 ID 的协议错误通过。
- IPv6 租约恢复的 128 字节行缓冲不能完整读取长记录，统一相关缓冲到 768 字节并修正空描述尾部扫描。新增超过 128 字节的恢复/续期/删除测试。
- IPv6 租约续期把传入 ID 写入其他行，并产生额外空行；修正后独立租约续期、删除、重启及 nonce/RemoteHost 恢复通过。
- fw4 的 forward 后置钩子在 WAN 拒绝之后，导致 API 成功而 IPv6 实际流量不通；改为前置钩子，用实际 TCP/UDP 收发验证。
- nft userdata 改为标准 comment TLV，兼容读取旧原始格式；界面读取真实 nft JSON。动态规则按接口名称匹配，避免 WAN 同名设备重建后旧 ifindex 失效。
- PCP 缺址不能误报为畸形请求；正常缺址/恢复只记录状态变化，预期离线发送失败降为 DEBUG，保留未知错误诊断。
- 反复修改设置时直接替换 procd 实例会消耗故障 respawn 预算；实际配置变化改用原生 restart，重复相同配置保持 PID。
- 首次冷启动发现 netifd 已发布设备但 LAN 路由尚未就绪，租约恢复校验会丢弃有效记录。启动流程等待 LAN 协议就绪，IPv4 缺址时延后恢复；最终再次重启通过。第一次启动记录不能作为通过证据。
- LuCI 关闭服务后 procd 的 UCI 触发器也被删除，重新勾选启用不会启动。禁用状态改为保留没有运行实例的 procd 服务与配置触发器，真实浏览器关闭/启用通过；生命周期回归改为直接发配置事件，不再用手动 reload 掩盖这个路径。
- 初次 LuCI 包目录层级不对，修正安装到 `/www/luci-static/` 后真实浏览器验证。

`first/second/third/fourth-functional-attempt.txt`、`lifecycle-first.json` 和首次 reboot 记录保留失败过程。`luci-browser-first/second-attempt.txt` 保留浏览器等待与导航的问题，`luci-browser-third-attempt.txt` 记录上述真实触发器缺陷，最终 `luci-browser.json` 为实际通过结果。部分初始失败来自测试脚本的等待窗口、Linux down 后自动删除 IPv6 地址、字符串格式或日志环形缓冲比较；这些与上列实际产品缺陷分别处理。额外保留 `after-reboot-attempt/`（该次只执行了主回归；后续组未运行，不沿用以前的 PASS 文件）：开机后立即运行时，日志显示 23:38:45 的 WAN6 初次 ifup 触发 fw4 reload，与第一批映射请求重叠；一次 PCP 转发失败后，未清理测试条目导致后续断言连带失败。再次运行未复现。由日志推断与启动阶段 fw4 规则空窗相关，不能把该次结果标为通过；实验脚本现先等待 VM WAN/WAN6 的 pending 协议初始化结束。

最终通过状态以 `repeat/`、`reboot-final.txt` 和最终浏览器结果为准。

SDK 构建日志仍包含 SDK 元数据的 bool/tristate 重定义提示及上游配置生成器的可选 UUID 提示；UUID 实际由 init 保存，未新增 libuuid。最终 daemon C 编译没有 warning/error。VM fw4 显示的 PassWall 无效 include 提示来自原有配置。

## 范围与限制

最终完整回归 45/45 通过（28+8+9）。两个客户端完成 320 次双栈 PCP 创建/删除，300 秒空闲期间 RSS 从 1048 KB 到 1044 KB，FD 保持 14 个、CPU ticks 增量 0；结束时 NAT/Pinhole 规则均为零，PID 不变。

300 秒空闲和限速负载中不出现重复动态规则、残留规则、异常重启、FD 增长或持续 RSS 增长；精确资源值见最终 soak 原始结果。这只是该时长和负载下的证据，不能据此声称永远不会泄漏。

IPv6 Pinhole 没有 IPv4 NAT 外部端口概念，LuCI 显示为横线；主机名称未解析时如实显示 Unknown。nft comment 最长 127 字节，较长描述在规则/查询/界面中可能截断。PCP nonce 不在界面展示。旧 IPv4 ACL 不自动变成 IPv6 ACL。

映射删除后测试新连接关闭；已有 conntrack 会话沿用系统正常语义。租约依赖正确时钟；旧 /etc 持久化配置实际变更会写 Flash，当前默认 /var 路径不写 Flash；空闲 IPv6 过期扫描不会反复改写文件。fw4 reload 与恢复信号之间存在短暂规则空窗。

尚未验证：aarch64/360T7 构建与刷机、固件 CI、真实 Windows/Apple/Xbox 等客户端、多天连续运行、Flash 寿命、目标硬件 offload/fullcone 与其他代理组件组合。协议支持结论来自报文与数据平面测试，不等同于所有消费设备互操作认证。

`final-cleanup-check.txt` 严格校验 network/firewall/upnpd 已恢复至实验前配置、没有残留实验 namespace，服务启用且运行。普通 WAN IPv4 的 HTTP 5000 连接被拒绝，见 `physical-wan-http.json`。最终 daemon/控制工具/init 文件 SHA256 与 IPK 内容一致，见 `build-manifest.json`、`installed-sha256.txt`。

测试结束恢复 VM 原网络/firewall 设置及普通 `upnpd` 配置，保留安装好的定制包和启用的服务；实验备份、测试工具与结果在 VM `/root/`，可按 README 回滚或使用用户快照。

## 2026-10-13 中文修复

此前仅验证英文页面，漏打包 UPnP 中文词典，导致共用词条为中文、应用词条仍为英文。LuCI 包升级为 23.05-custom-2，编译并安装标准 upnp.zh-cn.lmo，沿用固定 23.05 的 PO 词条并补齐新开关和菜单。47 个页面/菜单词条覆盖通过，zh-CN 浏览器的列表、删除、关闭/再启用和 JavaScript 检查通过，截图为 luci-zh.png、luci-zh-advanced.png。中文截图的主机浏览器使用 Noto CJK 字体，路由器未安装字体。

仅 LuCI 数据包变化，MiniUPnPd IPK SHA256 与原 45 项回归版本完全一致。更新中文包的干净重建校验通过，见 reproducible-i18n-build.txt。规则命名对照见 nft-format.md。

## 2026-10-13 恢复上游临时租约路径

按用户要求，默认配置、init 回退值、LuCI 提示和测试机 UCI 改为 /var/run/miniupnpd.leases 与 /var/run/miniupnpd.leases6。服务重启及 fw4 reload 仍能恢复有效租约，系统重启不再保留租约。先前 reboot-final.txt 的跨系统恢复结果属于旧 /etc 配置，不能用于描述新默认策略。boot-smoke.sh 的预期已改为服务启动、旧临时租约消失；本次路径修改未再次重启 VM。

本次两个包实际构建并升级测试机通过，var-lease-install.txt 确认运行配置使用上述 /var/run 路径。daemon ELF 校验值与原回归版本一致；boot-smoke.sh 只调整预期，没有把未执行的新 reboot 检查标为通过。
