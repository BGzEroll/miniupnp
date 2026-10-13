# 接入 360T7 CI

源码目录按 OpenWrt feed 结构分为 `net/miniupnpd` 和 `applications/luci-app-upnp`；`tests/` 和 `reports/` 不参与固件包编译。

针对 BGzEroll/BGzErol-OpenWRT-CI 的 `immortalwrt-23_05-360t7.yml`：

1. 将交付的 `upnp-ci-overlay.tar.gz` 解压到 CI 仓库根目录。包源码和替换脚本会位于 `custom/upnp/`。
2. 执行 `git apply custom/upnp/ci/immortalwrt-23_05-360t7.patch`。
3. 提交这些文件后运行原工作流。

新增步骤在 feeds 安装和自定义配置加载之后、`make defconfig` 之前。它移除构建树中旧 MiniUPnPd/LuCI 包链接、安装自维护包并选择 nftables/IPv6，不改其他目标的工作流，也不改 PassWall 包。再次执行脚本会更新同一受管理目录；已有实体旧包目录备份到构建树 `tmp/upnp-package-backup-*`。

中文词典直接包含在 `luci-app-upnp` 中，因此不要同时选择原 feed 的 `luci-i18n-upnp-zh-cn`。菜单名称为 UPnP，软件包名仍为 miniupnpd-nftables 和 luci-app-upnp。

本目录也可以单独发布为 Git 仓库，之后在 CI 中检出固定 commit 到 `custom/upnp/`，继续使用同一替换步骤。当前没有假定尚未提供的 UPnP 仓库 URL。

已验证替换脚本和 x86_64 SDK 构建；本次没有运行完整 360T7/aarch64 固件构建或推送远程 CI。
