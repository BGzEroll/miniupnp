#!/bin/sh
# Only the authorized test VM. Requires built packages, SDK and host Playwright.
set -eu
TASK_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TASK_VM=root@192.168.114.210
TASK_SDK="$TASK_ROOT/.work/sdk"
TASK_BROWSER_PYTHON=${BROWSER_PYTHON:-python3}
mkdir -p "$TASK_ROOT/reports/delete"
STAGING_DIR="$TASK_SDK/staging_dir/target-x86_64_musl" \
    "$TASK_SDK/staging_dir/toolchain-x86_64_gcc-12.3.0_musl/bin/x86_64-openwrt-linux-musl-gcc" \
    -shared -fPIC -Wall -Wextra -Werror -Os "$TASK_ROOT/tests/delete-fault.c" -ldl -o "$TASK_ROOT/.work/delete-fault.so"
ssh "$TASK_VM" 'set -e; test ! -e /root/upnp-lab-backup; test ! -e /tmp/upnp-delete-test.pid; if [ -d /root/upnp-delete-test-results ]; then mv /root/upnp-delete-test-results "/root/upnp-delete-test-results-$(date +%s)"; fi; mkdir /root/upnp-delete-test-results'
scp -O "$TASK_ROOT/tests/lab.sh" "$TASK_ROOT/tests/integration.py" "$TASK_ROOT/tests/delete-errors.py" "$TASK_ROOT/.work/delete-fault.so" "$TASK_VM:/tmp/"
restore_vm() {
    TASK_STATUS=$?
    trap - EXIT HUP INT TERM
    scp -O "$TASK_VM:/root/upnp-delete-test-results/*" "$TASK_ROOT/reports/delete/" || :
    if ! ssh "$TASK_VM" 'set -e; if [ -f /tmp/upnp-delete-test.pid ]; then TASK_PID=$(cat /tmp/upnp-delete-test.pid); if [ "$(readlink /proc/$TASK_PID/exe 2>/dev/null)" = /usr/sbin/miniupnpd ]; then kill -TERM "$TASK_PID"; sleep 1; fi; fi; rm -f /tmp/upnp-delete-test.pid /tmp/upnp-delete-fault.mode /tmp/upnp-delete-fault.ready /tmp/upnp-delete-fault.resume /tmp/upnp-delete-fault.so; /tmp/lab.sh cleanup'; then
        [ "$TASK_STATUS" != 0 ] || TASK_STATUS=1
    fi
    exit "$TASK_STATUS"
}
trap restore_vm EXIT HUP INT TERM
ssh "$TASK_VM" 'set -e; /tmp/lab.sh setup; /etc/init.d/miniupnpd stop; mv /tmp/delete-fault.so /tmp/upnp-delete-fault.so; : > /tmp/upnp-delete-fault.mode; : > /tmp/upnp-delete-fault.trace; nohup env LD_PRELOAD=/tmp/upnp-delete-fault.so /usr/sbin/miniupnpd -f /tmp/upnp-lab.conf > /root/upnp-delete-test-results/daemon.log 2>&1 </dev/null & echo $! > /tmp/upnp-delete-test.pid'
ssh "$TASK_VM" 'set -e; for i in 1 2 3 4 5 6 7 8 9 10; do [ ! -S /var/run/miniupnpd.ctl ] || break; sleep 1; done; python3 /tmp/delete-errors.py /root/upnp-delete-test-results/backend.json > /root/upnp-delete-test-results/backend.stdout 2>&1'
ssh "$TASK_VM" 'set -e; cp /tmp/upnp-delete-fault.trace /root/upnp-delete-test-results/trace.txt; kill -TERM $(cat /tmp/upnp-delete-test.pid); sleep 1; rm /tmp/upnp-delete-test.pid; rm -f /tmp/upnp-delete-fault.mode /tmp/upnp-delete-fault.ready /tmp/upnp-delete-fault.resume /tmp/upnp-delete-fault.so; /etc/init.d/miniupnpd start'
"$TASK_BROWSER_PYTHON" "$TASK_ROOT/tests/delete-browser.py"
