# ImmortalWrt 23.05 MiniUPnPd

面向 fw4/nftables 的 MiniUPnPd 定制包，支持 IPv4/IPv6、IGDv2、NAT-PMP 与 PCP MAP/ANNOUNCE。保留上游软件包名称、UCI 配置格式与 nft 链命名，LuCI 菜单名称为 UPnP，内置简体中文翻译。

## 目录

| 目录 | 内容 |
|---|---|
| miniupnpd | 包定义、服务集成、默认配置和源码补丁 |
| luci-app-upnp | LuCI 页面、RPC 与中文翻译 |
| scripts | 可选的本地 SDK 构建工具 |
| tests | 可复用的协议、生命周期、浏览器及共存测试工具 |
| docs | 上游对照与测试说明 |
| licenses | 上游许可证 |

源码版本、SDK、feeds 与补丁校验值固定在 [sources.json](sources.json)。上游基线为 MiniUPnP 2.3.11 后的 f8c4f4c3320820e615b281147b3043f66c195f17。

## OpenWrt / ImmortalWrt feed 接入

本仓库是标准的 OpenWrt 包 feed，CI 只需添加包源并使用 OpenWrt 自带的 feeds 工具，不调用本仓库的任何脚本。

在 23.05 源码的 feeds.conf.default 最前面添加：

```text
src-git --force custom_upnp https://github.com/BGzEroll/miniupnp.git;master
```

然后在全新的源码树中执行：

```sh
./scripts/feeds update -a
./scripts/feeds install -a
```

custom_upnp 放在最前面以优先提供同名包，--force 允许覆盖源码树中的同名核心包。自维护包会链接到 package/feeds/custom_upnp/。在固件配置中选择：

```text
CONFIG_IPV6=y
CONFIG_PACKAGE_miniupnpd-nftables=y
CONFIG_PACKAGE_luci-app-upnp=y
# CONFIG_PACKAGE_miniupnpd-iptables is not set
# CONFIG_PACKAGE_luci-i18n-upnp-zh-cn is not set
```

随后执行 make defconfig，再按正常流程下载和编译。中文翻译包含在 luci-app-upnp 内。BGzErol-OpenWRT-CI 的 23.05 x86 和 360 T7 已按此方式配置。

本地使用 src-link 时，链接目录应只包含两个包，避免扫描到 SDK 缓存。scripts/build.sh 会自动在 .work/custom-upnp-feed/ 生成这样的临时包源，其余包源保持固定版本。

## 可选的本地 SDK 构建

在 Linux x86_64 上执行：

```sh
./scripts/build.sh
```

脚本自动下载并校验 ImmortalWrt 23.05.4 x86_64 SDK，使用 GCC 12.3.0/musl、libmnl 1.0.5 和 libnftnl 1.2.6。主机需要常见 OpenWrt SDK 构建依赖，包括 make、gcc/g++、git、curl、Python 3、perl、patch、xz、file、rsync 等；首次构建需要约 4 GB 空间。

SDK 和下载缓存位于 .work/，IPK 与校验值输出到 artifacts/；两者不加入 Git。运行依赖为 libc、libmnl、libnftnl、libcap-ng、fw4 及现有 LuCI/RPC 组件。未提供 iptables 变体，未启用 PCP PEER。

## 安装与使用

安装 miniupnpd-nftables、luci-app-upnp 及其缺失依赖。生成的 x86_64 IPK 仅用于 ABI 匹配的 23.05 x86_64 系统；其他架构应从源码编译。中文词典已内置，不需要另装 luci-i18n-upnp-zh-cn。

全新安装默认关闭服务。标准 wan/wan6/lan 接口下，进入“服务 → UPnP”，勾选“启动 UPnP 与 NAT-PMP 服务”并保存应用即可；客户端需要主动申请映射。升级时 opkg 保留已有 UCI 配置，应核对旧协议开关和租约路径。

默认启用 IGDv2、NAT-PMP/PCP 和 IPv6 Pinhole，secure_mode=1，允许合法私网/CGNAT WAN 地址。默认 ACL 保持 Allow high ports、Default deny，只允许 1024–65535 的内外端口。NAT-PMP 与 PCP 沿用上游共享开关；不进行 daemon 自身的 STUN 探测。

IPv4/IPv6 租约文件分别为 /var/run/miniupnpd.leases 和 /var/run/miniupnpd.leases6。有效租约可在服务重启、stop/start 和 fw4 reload 后恢复；系统重启后清空，由客户端重新申请。默认不将租约写入 Flash。

## 本地修改

- 修正 IPv6 Pinhole 查询、计数、稳定 ID、租约读写与恢复，检查 SOAP 数字边界。
- nft 使用标准 comment TLV 和接口名称匹配，支持同名 WAN 设备重建。
- fw4 reload 向已有 daemon 发送恢复信号；配置未变化时避免重复重启，冷启动等待 LAN 就绪。
- 保留禁用状态的 procd 配置触发器，LuCI 可重新启用服务。
- LuCI 展示真实双栈规则，通过权限为 0600 的本地控制 socket 删除映射。

详见 [上游与补丁说明](docs/upstream.md)、[nft 命名对照](docs/nft-format.md)和[测试结果与复现](docs/testing.md)。fw4 reload 与租约恢复之间存在短暂规则空窗；已建立连接遵循正常 conntrack 行为。
