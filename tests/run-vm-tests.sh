#!/bin/sh
# This command alters ONLY the supplied test VM and restores its saved settings.
set -eu
TASK_VM=${1:-root@192.168.114.210}
TASK_ROOT=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
TASK_IDLE_SECONDS=${IDLE_SECONDS:-300}
# A failed early suite must not inherit later-suite PASS files from an old run.
if [ -d "$TASK_ROOT/reports/repeat" ]; then
	mv "$TASK_ROOT/reports/repeat" "$TASK_ROOT/reports/repeat-$(date +%s)"
fi
scp -O "$TASK_ROOT/tests/lab.sh" "$TASK_ROOT/tests/integration.py" "$TASK_ROOT/tests/extended.py" "$TASK_ROOT/tests/lifecycle.py" "$TASK_ROOT/tests/soak.py" "$TASK_VM:/tmp/"
ssh "$TASK_VM" 'if [ -d /root/upnp-test-results ]; then mv /root/upnp-test-results "/root/upnp-test-results-$(date +%s)"; fi; mkdir /root/upnp-test-results; /tmp/lab.sh setup'
restore_lab() {
	TASK_STATUS=$?
	trap - EXIT HUP INT TERM
	mkdir -p "$TASK_ROOT/reports/repeat"
	scp -O "$TASK_VM:/root/upnp-test-results/*" "$TASK_ROOT/reports/repeat/" || :
	ssh "$TASK_VM" '/tmp/lab.sh cleanup' || :
	exit "$TASK_STATUS"
}
trap restore_lab EXIT HUP INT TERM
ssh "$TASK_VM" 'python3 /tmp/integration.py /root/upnp-test-results/integration.json > /root/upnp-test-results/integration.stdout 2>&1'
ssh "$TASK_VM" 'python3 /tmp/lifecycle.py /root/upnp-test-results/lifecycle.json > /root/upnp-test-results/lifecycle.stdout 2>&1'
ssh "$TASK_VM" 'python3 /tmp/extended.py /root/upnp-test-results/extended.json > /root/upnp-test-results/extended.stdout 2>&1'
# Reject shell metacharacters in an overridable numeric test duration.
case "$TASK_IDLE_SECONDS" in ''|*[!0-9]*) echo 'Invalid IDLE_SECONDS' >&2; exit 2 ;; esac
# The duration is intentionally expanded here after numeric validation.
# shellcheck disable=SC2029
ssh "$TASK_VM" "python3 /tmp/soak.py /root/upnp-test-results/soak.json $TASK_IDLE_SECONDS > /root/upnp-test-results/soak.stdout 2>&1"
mkdir -p "$TASK_ROOT/reports/repeat"
scp -O "$TASK_VM:/root/upnp-test-results/*" "$TASK_ROOT/reports/repeat/"
