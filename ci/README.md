# 从 Load_custom_feeds.sh 接入 CI

将本项目推送到自己的 GitHub 仓库后，把 [Load_custom_feeds-upnp.sh](Load_custom_feeds-upnp.sh) 中的片段追加到 CI 的 `script/Load_custom_feeds.sh`。将 UPNP_REPO 改为真实仓库 URL，UPNP_BRANCH 改为推送的分支；本项目当前分支为 master。

脚本执行时位于 OpenWrt 源码根目录：先克隆本项目到 `tmp/custom-upnp-source`，再运行 `scripts/install-to-openwrt.sh --packages-only "$PWD"`，将两个包安装到 `package/custom-upnp/`。这些包作为构建树内包存在，后续标准 `scripts/feeds update -a` 和 `install -a` 会保留它们，不再安装同名原包。无需修改工作流步骤，也无需把本项目源码复制进 CI 仓库。

在 CI 的 `config/immortalwrt23_05-360t7.config` 中选择：

```text
CONFIG_IPV6=y
CONFIG_PACKAGE_miniupnpd-nftables=y
CONFIG_PACKAGE_luci-app-upnp=y
# CONFIG_PACKAGE_miniupnpd-iptables is not set
# CONFIG_PACKAGE_luci-i18n-upnp-zh-cn is not set
```

删除这些选项的旧重复行。中文词典已包含在 luci-app-upnp 中，菜单名为 UPnP。`--packages-only` 不创建或修改 `.config`，因为工作流稍后才加载你的固件配置。

之前提供的工作流“替换为自维护 UPnP 软件包”步骤不再需要；如果已经添加，将其删除。重复手动执行时请先处理 `tmp/custom-upnp-source` 中的旧检出；普通 CI 每次从新构建树开始。

默认不带 `--packages-only` 的安装模式仍保留，供本项目 SDK 构建或已加载 `.config` 的构建树使用。已验证 SDK 的实际 feeds 安装和配置扫描；尚未运行完整 360T7/aarch64 固件 CI。
