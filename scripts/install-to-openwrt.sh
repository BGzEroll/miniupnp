#!/bin/sh
# Default: run after feeds installation and .config loading.
# --packages-only: run before feeds update; the firmware config selects packages.
set -eu
TASK_SOURCE=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TASK_MODE=full
if [ "${1:-}" = --packages-only ]; then
	TASK_MODE=packages-only
	shift
fi
TASK_TARGET=${1:?Usage: install-to-openwrt.sh [--packages-only] OPENWRT_ROOT}
python3 - "$TASK_SOURCE" "$TASK_TARGET" "$TASK_MODE" <<'PY'
import pathlib,re,shutil,sys,time
source=pathlib.Path(sys.argv[1]).resolve();target=pathlib.Path(sys.argv[2]).resolve()
assert (target/'rules.mk').is_file() and (target/'scripts/feeds').is_file(), 'Not an OpenWrt build tree'
packages_only=sys.argv[3]=='packages-only'
if not packages_only:assert (target/'.config').is_file(), 'Load the firmware .config before replacing UPnP'
destination=target/'package/custom-upnp'
assert not destination.is_symlink(), 'Refusing a symlink at package/custom-upnp'
assert not destination.exists() or (destination/'.managed-by-upnp').is_file(), 'Destination is not managed by this installer'
recipes={'miniupnpd':source/'net/miniupnpd','luci-app-upnp':source/'applications/luci-app-upnp'}
for recipe in recipes.values():assert (recipe/'Makefile').is_file(),recipe
backup=target/'tmp'/('upnp-package-backup-'+str(time.time_ns()))
names=('miniupnpd','luci-app-upnp','luci-i18n-upnp-zh-cn')
for name in names:
    candidates=[target/'package'/name,*sorted((target/'package/feeds').glob('*/'+name))]
    for path in candidates:
        if path.is_symlink():
            path.unlink();print('移除旧包链接：',path.relative_to(target))
        elif path.exists():
            saved=backup/path.relative_to(target);saved.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(path),str(saved));print('备份旧包目录：',path.relative_to(target))
destination.mkdir(parents=True,exist_ok=True)
(destination/'.managed-by-upnp').write_text('Managed by custom UPnP installer\n')
for name,recipe in recipes.items():
    path=destination/name
    if path.is_symlink():path.unlink()
    elif path.exists():shutil.rmtree(path)
    shutil.copytree(recipe,path);print('安装自维护包：',path.relative_to(target))
if not packages_only:
    config=target/'.config';lines=config.read_text().splitlines()
    keys=('CONFIG_PACKAGE_miniupnpd','CONFIG_PACKAGE_miniupnpd-nftables','CONFIG_PACKAGE_miniupnpd-iptables',
          'CONFIG_PACKAGE_luci-app-upnp','CONFIG_PACKAGE_luci-i18n-upnp-zh-cn','CONFIG_IPV6')
    lines=[line for line in lines if not any(re.match(r'^(?:# )?'+re.escape(key)+r'(?:=| is not set$)',line) for key in keys)]
    lines+=['CONFIG_IPV6=y','CONFIG_PACKAGE_miniupnpd-nftables=y','CONFIG_PACKAGE_luci-app-upnp=y',
            '# CONFIG_PACKAGE_miniupnpd-iptables is not set','# CONFIG_PACKAGE_luci-i18n-upnp-zh-cn is not set']
    config.write_text('\n'.join(lines)+'\n')
for name in ('.packageinfo','.packagedeps','.config-package.in'):
    (target/'tmp'/name).unlink(missing_ok=True)
print('UPnP 源码替换完成；请在固件配置选择 miniupnpd-nftables 和 luci-app-upnp。' if packages_only else 'UPnP 替换完成；接下来执行 make defconfig。中文词典已包含在 luci-app-upnp 中。')
PY
