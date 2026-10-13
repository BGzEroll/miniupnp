#!/bin/bash
# 将这段追加到 CI 的 script/Load_custom_feeds.sh，当前目录是 OpenWrt 源码根目录。
# 修改为推送后的真实仓库 URL 和分支。
UPNP_REPO='https://github.com/BGzEroll/你的UPnP仓库.git'
UPNP_BRANCH='master'
git clone --depth 1 --branch "$UPNP_BRANCH" "$UPNP_REPO" tmp/custom-upnp-source || exit 1
bash tmp/custom-upnp-source/scripts/install-to-openwrt.sh --packages-only "$PWD" || exit 1
