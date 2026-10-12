#!/bin/sh
# Build and run selected upstream regression tests using the same pinned patches.
set -eu
TASK_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TASK_VM=${1:-root@192.168.114.210}
TASK_SDK="$TASK_ROOT/.work/sdk"
TASK_TARGET="$TASK_SDK/staging_dir/target-x86_64_musl"
TASK_TOOLCHAIN="$TASK_SDK/staging_dir/toolchain-x86_64_gcc-12.3.0_musl"
TASK_TEST_SOURCE="$TASK_ROOT/.work/unit-source"
# Refresh only this script's generated source tree, never a user checkout.
python3 - "$TASK_TEST_SOURCE" <<'PY'
import pathlib,shutil,sys
p=pathlib.Path(sys.argv[1]);shutil.rmtree(p,ignore_errors=True);p.mkdir(parents=True)
PY
tar -xzf "$TASK_SDK/dl/miniupnp-f8c4f4c3320820e615b281147b3043f66c195f17.tar.gz" -C "$TASK_TEST_SOURCE" --strip-components=1
for patchfile in "$TASK_ROOT"/package/miniupnpd/patches/*.patch; do patch -d "$TASK_TEST_SOURCE" -p1 < "$patchfile"; done
export STAGING_DIR_HOST="$TASK_SDK/staging_dir/host"
export STAGING_DIR="$TASK_TARGET"
export STAGING_PREFIX="$TASK_TARGET/usr"
export PATH="$TASK_TOOLCHAIN/bin:$TASK_SDK/staging_dir/host/bin:$PATH"
export PKG_CONFIG_LIBDIR="$TASK_TARGET/usr/lib/pkgconfig"
export PKG_CONFIG_PATH="$TASK_TARGET/usr/lib/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR="$TASK_TARGET"
export DEBUG=''
cd "$TASK_TEST_SOURCE/miniupnpd"
echo 23.05.4 > os.openwrt
# No Git introspection from the surrounding maintenance checkout.
printf '%s\n' 'GITREF := pinned-source-tests' > gitrev.mk
./configure --disable-fork --disable-pppconn --firewall=nftables --ipv6 --igd2 --leasefile --portinuse --regex --vendorcfg
make -j"${JOBS:-4}" CC=x86_64-openwrt-linux-musl-gcc CFLAGS="-Os -I$TASK_TARGET/usr/include" LDFLAGS="-L$TASK_TARGET/usr/lib" TESTS=1
ssh "$TASK_VM" 'mkdir -p /tmp/upnp-unit'
scp -O testupnppermissions testupnppermissions.sh testgetifaddr testgetifaddr.sh testssdppktgen testupnphttp testupnphttp.sh "$TASK_VM:/tmp/upnp-unit/"
ssh "$TASK_VM" 'cd /tmp/upnp-unit && sh testupnppermissions.sh && sh testgetifaddr.sh && ./testssdppktgen && python3 -c '\''import subprocess; subprocess.run(["sh", "testupnphttp.sh"],check=True,timeout=30)'\'''
