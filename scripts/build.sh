#!/bin/sh
# Reproducible x86_64 package build; aarch64 and firmware CI are outside scope.
set -eu
TASK_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TASK_WORK="$TASK_ROOT/.work"
TASK_SDK="$TASK_WORK/sdk"
TASK_CORE="$TASK_WORK/core"
TASK_CORE_COMMIT=bae54687c709f20f0dc18cef033e0bad0159ea23
TASK_SDK_FILE=immortalwrt-sdk-23.05.4-x86-64_gcc-12.3.0_musl.Linux-x86_64.tar.xz
TASK_SDK_HASH=937dcb18126d75068e0a2f7f0f48ed95f9a1cedfa39d9ad47f505d595df1074c
mkdir -p "$TASK_WORK" "$TASK_ROOT/artifacts"
if [ ! -f "$TASK_SDK/rules.mk" ]; then
	curl -fL "https://downloads.immortalwrt.org/releases/23.05.4/targets/x86/64/$TASK_SDK_FILE" -o "$TASK_WORK/sdk.tar.xz"
	printf '%s  %s\n' "$TASK_SDK_HASH" "$TASK_WORK/sdk.tar.xz" | sha256sum -c -
	mkdir -p "$TASK_SDK"
	tar -xJf "$TASK_WORK/sdk.tar.xz" -C "$TASK_SDK" --strip-components=1
fi
if [ ! -d "$TASK_CORE/.git" ]; then
	git clone --depth 1 --branch v23.05.4 --filter=blob:none --sparse https://github.com/immortalwrt/immortalwrt.git "$TASK_CORE"
	git -C "$TASK_CORE" sparse-checkout set package/libs/libmnl package/libs/libnftnl
fi
[ "$(git -C "$TASK_CORE" rev-parse HEAD)" = "$TASK_CORE_COMMIT" ] || { echo 'Unexpected core recipe revision' >&2; exit 1; }
mkdir -p "$TASK_SDK/package/libs"
cp -a "$TASK_CORE/package/libs/libmnl" "$TASK_CORE/package/libs/libnftnl" "$TASK_SDK/package/libs/"
cat > "$TASK_SDK/feeds.conf.default" <<'EOT'
src-git packages https://github.com/immortalwrt/packages.git^9d567f8ed5f99833e4bffe734e047d0a01b57ce5
src-git luci https://github.com/immortalwrt/luci.git^d4189db0d76c02e24087298327ec40a59fcfb2aa
EOT
(cd "$TASK_SDK" && ./scripts/feeds update packages luci && ./scripts/feeds install libcap-ng luci-base)
# Build LuCI's standard PO compiler on the host; do not install/upgrade luci-base on the VM.
(cd "$TASK_SDK/feeds/luci/modules/luci-base" && make TOPDIR="$TASK_SDK" HOST_BUILD_PREFIX="$TASK_SDK/staging_dir/hostpkg" host-compile host-install V=s)
for package in miniupnpd luci-app-upnp; do
	if [ -e "$TASK_SDK/package/$package" ] || [ -L "$TASK_SDK/package/$package" ]; then
		[ "$(readlink "$TASK_SDK/package/$package")" = "$TASK_ROOT/package/$package" ] || { echo "Package path already occupied: $package" >&2; exit 1; }
	else
		ln -s "$TASK_ROOT/package/$package" "$TASK_SDK/package/$package"
	fi
done
cat > "$TASK_SDK/.config" <<'EOT'
CONFIG_ALL=n
CONFIG_ALL_KMODS=n
CONFIG_ALL_NONSHARED=n
CONFIG_DEVEL=y
CONFIG_IPV6=y
CONFIG_PACKAGE_miniupnpd-nftables=m
CONFIG_PACKAGE_luci-app-upnp=m
CONFIG_PACKAGE_libcap-ng=y
CONFIG_PACKAGE_libmnl=y
CONFIG_PACKAGE_libnftnl=y
EOT
(cd "$TASK_SDK" && make defconfig && make package/miniupnpd/clean && make package/miniupnpd/compile -j"${JOBS:-4}" V=s)
# LuCI consists of data files and is built through the SDK package recipe.
# Its existing runtime dependencies are not rebuilt or upgraded on the VM.
(cd "$TASK_ROOT/package/luci-app-upnp" && make TOPDIR="$TASK_SDK" compile V=s)
cp "$TASK_SDK"/bin/packages/x86_64/base/miniupnpd-nftables_*.ipk "$TASK_ROOT/artifacts/"
cp "$TASK_SDK"/bin/packages/x86_64/base/luci-app-upnp_23.05-custom-2_all.ipk "$TASK_ROOT/artifacts/"
if [ -f "$TASK_ROOT/artifacts/luci-app-upnp_23.05-custom-1_all.ipk" ]; then
	mv "$TASK_ROOT/artifacts/luci-app-upnp_23.05-custom-1_all.ipk" "$TASK_WORK/"
fi
cp "$TASK_SDK"/bin/packages/x86_64/packages/libcap-ng_*.ipk "$TASK_ROOT/artifacts/"
(cd "$TASK_ROOT/artifacts" && sha256sum ./*.ipk > SHA256SUMS)
