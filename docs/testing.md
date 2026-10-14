# 测试结果与复现

以下是 2026-10-12 至 2026-10-13 在 ImmortalWrt 23.05 x86_64 VM 上取得的历史测试结果。本次目录清理没有重新运行 VM 全套测试。

| 检查 | 结果 |
|---|---|
| 主协议与实际转发回归 | 28/28 通过 |
| 生命周期与 WAN 设备重建 | 8/8 通过 |
| 扩展协议、租约与边界 | 9/9 通过 |
| 并发负载 | 两个客户端完成 320 次双栈 PCP 创建/删除 |
| 300 秒空闲 | RSS 1048 → 1044 KiB，FD 14，CPU ticks 增量 0，PID 不变，无残留映射 |
| LuCI | 双栈列表、删除、服务开关、47 个中文词条及菜单验证通过 |
| PassWall nft 共存 | 6/6 通过，含双栈 TCP/UDP 转发、双方规则重载、代理链计数命中、删除清理 |
| 旧安装器包替换（历史） | 无配置安装、配置保留、重复执行及真实 SDK feeds install -a / defconfig 通过；该安装器已移除 |

PassWall 检查使用测试机 4.78-1 的实际 nft 生成器及隔离接口，没有启动外部代理节点。尚未验证完整 360T7/aarch64 固件构建、真实 Windows/Apple/Xbox 客户端、硬件 offload/fullcone 组合及多天运行。

当前默认租约为 /var/run/miniupnpd.leases 和 /var/run/miniupnpd.leases6。服务重启与 fw4 reload 可恢复有效租约，系统重启后清空。早期使用 /etc 路径的跨系统租约恢复记录不代表当前默认行为；修改路径后未再次重启 VM 验证。

## 重复运行

协议测试需要 VM 上的 Python 3 light、ip-full、macvlan 和桥支持。以下脚本会在目标 VM 创建不连接物理端口的隔离拓扑并恢复配置，执行前确认目标地址。

```sh
./tests/run-vm-tests.sh root@192.168.114.210
./tests/run-passwall-test.sh
python3 tests/check-translations.py
```

主回归默认包含真实 120 秒 PCP 租约等待和 300 秒空闲监测。可用 IDLE_SECONDS 调整空闲时长。实验中断后，按实际情况执行 VM /tmp/lab.sh cleanup；配置备份保留在 VM /root/upnp-lab-backup-*。

LuCI 浏览器检查使用 tests/run-luci-test.sh，主机需要 Playwright/Chromium；BROWSER_PYTHON 可指定 Python，BROWSER_LOCALE=zh-CN 可检查中文，截图需要主机中文字体。上游 C 测试使用 tests/upstream-tests.sh，须先完成 scripts/build.sh 以生成 SDK。tests/boot-smoke.sh 在 VM 上分别执行 setup、重启、check、cleanup，用于检查冷启动和临时租约策略。

新测试输出写入 reports/，新构建输出写入 artifacts/，这些生成目录不加入 Git。详细旧报告、失败过程、截图和已构建 IPK 已归档到开发机项目目录之外；此前 Git 提交也保留原报告。

## 标准 feed 目录迁移

包目录改为根目录的 miniupnpd/ 和 luci-app-upnp/，包定义、补丁及运行文件内容保留，翻译文件只更新路径注释。旧安装器与对应测试移除，CI 使用正常 feeds 流程。

本轮标准 feed 安装、两个 23.05 目标 defconfig 及 x86 SDK 包编译通过，未重新进行 VM 协议测试。编译产物和临时 SDK 已清理。

## 当前布局复核

保持根目录 miniupnpd/ 和 luci-app-upnp/ 的结构。路径、文档链接、Python/JSON/Shell 语法、47 个中文词条以及补丁 SHA256 检查通过；包运行文件与迁移前一致，PO 文件仅改变路径注释。

实际 x86_64 SDK 构建发现并修正本地 build.sh 的两处问题：整个项目作为 src-link 时会扫入 .work 下的 SDK；在 feed 更新前写入配置会导致更新时丢失包选择。现在仅暴露两个包目录，在 feeds 准备好之后写配置，并检查包选择及预期 IPK 是否存在。修正后两个包实际编译、打包通过，没有循环扫描；daemon、控制工具和 init 的 SHA256 与之前 VM 验证版本相同。

本轮未重跑 VM 协议回归或完整固件 CI。原始构建日志、验证结果与 IPK 在开发机项目外归档，临时 SDK 已清理。

## 删除异常处理修复（2026-10-14）

包版本更新为 miniupnpd-nftables 2.3.11-git20261009-4、luci-app-upnp 23.05-custom-5。测试机实际升级，原目录布局、UCI 格式、nft 命名和默认租约路径保持原样。没有新增运行依赖、守护进程、配置项或删除重试机制。

专项后端检查 17/17 通过：IPv4 成对规则事务删除、重复删除、发送/查询失败、事务第一条或第二条操作被真实内核拒绝、IPv6 删除失败、规则在删除前被清空、部分规则已被外部删除、混合到期清理、内核 ACK 丢失后的状态确认、外部规则恢复后刷新缓存，以及故障后的下一次请求与 PID/FD 稳定性。失败时规则和租约保留；到期成功的 UID 立即清理，失败的 UID 保留。

浏览器专项检查 7/7 通过：正常删除、后台 Failed、返回内容缺少 result、通信失败、删除已经执行但回复丢失、条目已不存在、刷新失败。检查中文通知、按钮恢复、实际列表及服务状态，没有 JavaScript 异常；50 个页面/菜单词条覆盖通过。初次渲染和轮询的按钮都绑定到对应 view 实例。

故障注入通过 tests/delete-fault.c 编译的临时 LD_PRELOAD 库完成，不含在 IPK 中，也没有在生产代码留下测试开关。修改删除请求中的 handle 让内核拒绝实际事务，并观察规则回滚；丢弃实际 ACK 模拟已提交但回应不可用的情形。首次辅助脚本的缓存假设及 daemon 子进程权限假设曾导致失败；复核也发现 nft 与租约文件时间不足一秒的边界，最终改为按成功删除的 UID 清理，保留原始失败记录。

复现专项测试须先构建并安装本次两个包，主机准备 Playwright/Chromium，然后执行：

```sh
BROWSER_PYTHON=/path/to/playwright/python ./tests/run-delete-tests.sh
```

脚本目标固定为授权 VM root@192.168.114.210，会建立隔离实验、暂时加载故障库，完成检查后移除故障环境并恢复配置。结果输出到 reports/delete/ 和 reports/delete-browser.json。本轮没有进行 aarch64/360T7 固件、刷机或外部代理节点验证。

专项检查还覆盖“缓存曾记录条目不存在，但外部恢复了规则”的情况；每次删除前读取当前规则，避免凭旧缓存返回已不存在。对内核回应丢失，失败后仅查询实际状态：确认已消失则清理租约，无法确认则保留并报告失败。

一次完整回归在续租后的 conntrack 证据断言处失败；实际转发成功，单独复现及后续重跑未复现，首个失败遗留映射导致后续断言连带失败。原始失败记录保留，未把该次结果标为通过；测试现在在证据断言失败时保存完整 conntrack 快照，未放宽原有断言。

最终版本完整回归 45/45 通过（主协议 28、生命周期 8、扩展 9），包括真实双栈 TCP/UDP 转发、租约到期、fw4 reload、服务重启、同名 WAN 设备重建及安全边界。另完成 320 次并发双栈 PCP 创建/删除；本轮空闲观察为 60 秒，RSS 1048 → 1044 KiB、FD 保持 14、空闲 CPU ticks 增量 0、PID 不变且无残留规则。该时长不等同于多天稳定性证明。

正常 LuCI 双栈列表、实际删除及保存应用的禁用/再启用也通过。测试结束逐项核对 network/firewall/upnpd 与安装前备份一致；无实验 namespace、故障库或故障进程残留，定制服务启用并运行，列表为空。
