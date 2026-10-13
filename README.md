# ImmortalWrt 23.05 MiniUPnPd 定制包

面向 Linux、fw4/nftables，默认 IGDv2、IPv6、NAT-PMP/PCP 同时工作，私有 IPv4 和 CGNAT 不作为本级映射的拒绝条件。保留 23.05 的 `upnpd.config`、`perm_rule` 和 LuCI 页面交互。当前交付 x86_64；aarch64、360T7 和固件 CI 未实施。

- `package/miniupnpd/`：固定上游源码、OpenWrt 包、procd/hotplug/fw4 集成及四组补丁。
- `package/luci-app-upnp/`：23.05 页面，内置标准简体中文 LMO 翻译，读取真实 nft JSON、展示 IPv6 Pinhole，通过 root 专用控制接口删除实际映射。
- `scripts/`：构建、隔离拓扑、协议与数据转发测试、扩展测试及资源监测。
- `sources.json`、`reports/upstream.md`：源码锁定及选用理由。
- `reports/`：实际通过/失败记录、日志、规则和浏览器证据。
- [测试报告](reports/TEST-REPORT.md)：最终结果、修复过程及尚未验证的范围。
- `artifacts/`：本机生成的 IPK 和 SHA256SUMS；二进制不加入 Git。

## 构建

在 Linux x86_64 上执行：

```sh
./scripts/build.sh > reports/rebuild.log 2>&1
```

首次自动下载并校验 ImmortalWrt **23.05.4** SDK（GCC 12.3.0/musl）。包使用 libmnl 1.0.5、libnftnl 1.2.6，符合测试机原有 ABI。不会升级测试机内核、libc 或 fw4。SDK、下载缓存及上游检出放在 `.work/`；需要约 4 GB 磁盘空间和常见 OpenWrt SDK 主机构建依赖（make、gcc/g++、git、curl、Python 3、perl、patch、xz、file、rsync 等）。

运行依赖是 libc、libmnl、libnftnl、libcap-ng 和已有 fw4。UUID 在 init 中由内核生成并保存到 UCI，因此无需新增 libuuid 依赖。没有 iptables 变体、旧 PPP 描述或 PCP PEER/SNAT 链。STUN 源码仍保留在上游中，但此包生成的配置固定不使用它，LuCI 不提供相应设置。

源码 tar 的 SHA256、SDK SHA256、feeds/core commit 均固定。`--version` 的编译日期受 SDK 的 `SOURCE_DATE_EPOCH` 影响；判定源码版本应使用包版本、上游 commit 和补丁校验值。

## 安装及启用

仅在这次授权的测试 VM 或同 ABI 的 23.05 x86_64 系统使用生成的二进制：

```sh
scp -O artifacts/*.ipk root@192.168.114.210:/tmp/
ssh root@192.168.114.210
opkg install /tmp/libcap-ng_*.ipk /tmp/miniupnpd-nftables_*.ipk /tmp/luci-app-upnp_*.ipk
/etc/init.d/rpcd restart
uci set upnpd.config.enabled='1'
uci commit upnpd
/etc/init.d/miniupnpd enable
/etc/init.d/miniupnpd reload
```

已有配置由 opkg 保留，新默认配置可能放在 `/etc/config/upnpd-opkg`。旧配置的 `igdv1=1`、`ipv6_disable=1` 或 `/var/run` 租约路径也会保留；迁移时应核对这些值。不要同时安装旧的 iptables 变体。

主要设置：

| UCI 项 | 默认值与含义 |
|---|---|
| `enabled` | 新安装为 `0`，在 LuCI 开启后服务自动运行 |
| `enable_upnp` | `1`，UPnP 控制服务 |
| `enable_natpmp` | `1`，同时控制 NAT-PMP 和 PCP，沿用上游的共享开关 |
| `igdv1` | `0`，默认 IGDv2；IGDv1 SOAP/SSDP 及上游的 Microsoft 客户端兼容行为保留 |
| `ipv6_disable` | `0`，允许 IPv6 Pinhole |
| `secure_mode` | `1`，IPv4 SOAP 映射仅能指向请求者；PCP 第三方映射固定关闭 |
| `ext_allow_private_ipv4` | `1`，允许私网、CGNAT 等合法本级 WAN 地址 |
| `external_iface` / `external_iface6` | `wan` / `wan6`，OpenWrt 逻辑接口 |
| `internal_iface` | `lan`，可配置多个逻辑 LAN 接口 |
| `log_output` | `0`；开启时增加 INFO 请求日志，不全局屏蔽 syslog/stderr |
| `upnp_lease_file` / `upnp_lease_file6` | `/var/run/miniupnpd.leases` / `/var/run/miniupnpd.leases6`，服务重启可恢复，系统重启后清空 |

`perm_rule` 保留旧 IPv4 ACL 格式，默认仅允许 1024–65535 内外端口。IPv6 使用同一请求者、可路由 LAN 地址、TCP/UDP、非特权端口等检查；旧 IPv4 地址 ACL **不扩展解释为 IPv6 ACL**。服务不对外网可达性作承诺，只操作本机 NAT/防火墙。有效时间依赖系统时钟正确；无法凭租约文件证明断电前尚未写入的数据。

`config_file` 是原有专家配置入口，隔离测试使用它；普通使用请保持未设置，以便 LuCI/UCI 的设置和安全默认值生效。

## 生命周期

默认只有一个 MiniUPnPd 进程，没有新增网络监控守护进程。

- 地址和链路变化使用 MiniUPnPd 的 netlink 观察器；无 IPv4 时拒绝新的 IPv4 映射，IPv6 继续独立工作。
- WAN 缺址状态只在状态变化时记录，预期的网络错误不会被误报为 PCP 报文格式错误。
- nft 规则按接口**名称**匹配，避免同名 WAN 设备重建后 ifindex 变化使旧映射失效。
- fw4 加载完规则后向服务发 SIGUSR2；daemon 清理 nft 缓存、恢复有效租约，保留 IPv6 Pinhole ID。
- 重复 UCI/hotplug 事件且配置未变化时不重启。LAN 绑定地址、协议策略或配置实际变化时，调用原生 restart，清理本包链并重置真实故障的重试预算。
- 冷启动等待配置的 LAN 完成 netifd 协议初始化，再加载租约，避免设备已出现、地址和路由尚未就绪时误删有效租约。
- 在 LuCI 禁用时保留空的 procd 服务和配置触发器，重新启用无需手动调用 reload；没有运行 daemon 实例。
- `stop` 清空本包链，保留有效租约；后续 `start` 可以恢复。关闭 IPv6 时不恢复 IPv6 规则。
- LuCI 按稳定的协议/端口或 Pinhole ID 删除，通过现有 daemon 本地 Unix socket 串行处理，不按文件行号删除、不重启服务。socket 权限为 0600。

fw4 在装载新规则和租约恢复之间有短暂窗口。删除/过期测试检查的是**新连接**；已有 conntrack 会话遵循 fw4 的正常连接跟踪行为。网络断线恢复允许邻居发现收敛，测试采用 5 秒的恢复上限。

租约沿用上游 `/var/run` 临时文件路径，默认不写 Flash。服务 restart、stop/start 和 fw4 reload 可恢复尚未过期的租约；系统重启后租约文件清空，由客户端重新申请。IPv6 清理仅在确实有过期规则时改写文件。

## 重复测试

测试依赖 Python 3（light 标准库）、ip-full、已有 macvlan 和桥支持，**不是生产包依赖**。测试工具在 VM 内建立两个不接任何物理端口的空桥及三个 network namespace。无需 veth/tun 内核模块，无需改生产主路由的路由或 PVE 网络。

```sh
# 已安装本次两个 IPK、Python 3 后，在本机执行：
./scripts/run-vm-tests.sh root@192.168.114.210
# 延长空闲监测，例如一小时：
IDLE_SECONDS=3600 ./scripts/run-vm-tests.sh root@192.168.114.210
```

默认包括快速主回归、UCI 开关及同名 WAN 重建测试、需要等待真实 120 秒 PCP 租约的扩展测试，以及并发负载后的 300 秒空闲监测。测试在 VM `/root/upnp-test-results/` 留下原始证据，主机收集到 `reports/repeat/`。中断后可执行 `ssh root@192.168.114.210 /tmp/lab.sh cleanup`。拓扑配置备份在 VM `/root/upnp-lab-backup-*`。再次运行会先归档旧结果到 `reports/repeat-时间戳` 和 VM `/root/upnp-test-results-时间戳`，失败时不会混入上次后续测试的 PASS 文件。

首次获取 Python 等测试依赖应使用与系统 ABI 兼容的 23.05 软件源，核对下载 SHA256；测试机原来的 vsean SNAPSHOT 镜像已不可访问，不要为此升级整个系统或强装不同内核的 kmod。

`scripts/upstream-tests.sh` 使用相同 SDK 和补丁构建并运行上游权限、接口地址、SSDP 和 HTTP 测试。`scripts/boot-smoke.sh` 需复制到 VM 的 `/root/`，依次执行 `setup`、重启 VM、`check`、`cleanup`，在不接物理端口的虚拟 LAN 上检查系统重启后服务自动启动且临时租约不恢复。必须先确认 `check` 成功再执行清理。

`scripts/run-luci-test.sh` 自动建立隔离实验和浏览器测试映射，再调用 `scripts/luci-browser.py`。主机需安装 Playwright/Chromium，可通过 `BROWSER_PYTHON` 指定已安装 Playwright 的 Python。检查双栈列表、删除和“保存并应用”的启用/关闭操作，结果写入 `reports/luci-browser.json`；结束自动恢复实验配置。设置 `BROWSER_LOCALE=zh-CN` 可验证简体中文词条及菜单；主机需有中文字体才能生成正常的中文截图。`python3 scripts/check-translations.py` 检查页面与菜单的完整翻译覆盖。

## 回滚

测试前原始配置和运行信息已保存在 VM `/root/upnp-baseline/`，用户另有 PVE 快照。实验网络结束时自动恢复保存的 network/firewall/upnpd 配置。要回到最初完全未安装 UPnP 的状态，可先停止并禁用服务、卸载两个 UPnP 包，移除 `firewall.miniupnpd` include，再恢复 `/root/upnp-baseline/config.tgz` 中对应的配置；或使用用户已经创建的 VM 快照。不要把实验配置备份覆盖到其他设备。

360T7/aarch64 构建、CI 集成、真实 Windows/Apple/Xbox 客户端和多天运行证明均属于后续验证范围；本次没有访问或修改生产主路由、PVE 宿主机。

## 菜单与附加功能

菜单名称为 UPnP，软件包名称仍为 luci-app-upnp。正常新安装、标准 wan/wan6/lan 接口下，勾选启用并保存应用即可启动；客户端须主动申请映射。默认协议为 IGDv2、NAT-PMP/PCP 和 IPv6，secure_mode 与高端口 ACL 保持启用。

所参考的 OpenWrt 包默认 use_stun=0，本版普通 UCI 配置固定 ext_perform_stun=no 并移除设置入口。它只关闭 MiniUPnPd 自身的外部地址探测，不影响客户端软件自身的 STUN。PCP PEER 是控制到指定远端的出站映射和寿命的可选操作；上游 OpenWrt 构建参数也未启用 --pcp-peer，本版保留常用 PCP MAP 和 ANNOUNCE。

PassWall 与 UPnP 同时启用的组合尚未验证，测试时 PassWall enabled=0，不能宣称完全兼容。透明代理模式和流量排除策略可能影响同一数据路径，须另行做实际组合测试。
