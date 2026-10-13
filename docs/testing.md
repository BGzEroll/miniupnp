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
