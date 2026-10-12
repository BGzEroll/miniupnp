#!/bin/sh
# Run only on the authorized VM. setup -> VM reboot -> check -> cleanup.
set -eu
TASK_BACKUP=/root/upnp-boot-backup
case "${1:-}" in
setup)
	[ ! -e "$TASK_BACKUP" ] || { echo 'Boot test backup already exists' >&2; exit 1; }
	mkdir "$TASK_BACKUP"
	cp /etc/config/network /etc/config/upnpd "$TASK_BACKUP/"
	cp /var/run/miniupnpd.leases "$TASK_BACKUP/leases"
	cp /var/run/miniupnpd.leases6 "$TASK_BACKUP/leases6"
	cat /proc/sys/kernel/random/boot_id > "$TASK_BACKUP/boot_id"
	/etc/init.d/miniupnpd stop
	uci -q batch <<'EOT'
set network.upnpbootdev=device
set network.upnpbootdev.type='bridge'
set network.upnpbootdev.name='upnp-boot'
set network.upnpbootdev.bridge_empty='1'
set network.upnpboot=interface
set network.upnpboot.proto='static'
set network.upnpboot.device='upnp-boot'
set network.upnpboot.force_link='1'
set network.upnpboot.ipaddr='198.18.254.1'
set network.upnpboot.netmask='255.255.255.0'
set network.upnpboot.ip6addr='fd42:254::1/64'
set upnpd.config.internal_iface='lan upnpboot'
set upnpd.config.enabled='1'
set upnpd.config.upnp_lease_file='/var/run/miniupnpd.leases'
set upnpd.config.upnp_lease_file6='/var/run/miniupnpd.leases6'
commit network
commit upnpd
EOT
	/etc/init.d/network reload
	sleep 2
	TASK_EXPIRY=$(($(date +%s) + 600))
	printf 'TCP:51900::198.18.254.2:51901:%s:boot-smoke\n' "$TASK_EXPIRY" > /var/run/miniupnpd.leases
	printf 'TCP;fd42:254::2;51902;;0;1234;%s;boot-smoke\n' "$TASK_EXPIRY" > /var/run/miniupnpd.leases6
	/etc/init.d/miniupnpd enable
	/etc/init.d/miniupnpd restart
	;;
check)
	[ "$(cat /proc/sys/kernel/random/boot_id)" != "$(cat "$TASK_BACKUP/boot_id")" ]
	/etc/init.d/miniupnpd enabled
	/etc/init.d/miniupnpd running
	# Standard /var leases are intentionally lost on a system reboot.
	! nft list chain inet fw4 upnp_prerouting | grep -q '198.18.254.2:51901'
	! nft list chain inet fw4 upnp_forward | grep -q 'pinhole-1234'
	test -f /var/run/miniupnpd.leases && test ! -s /var/run/miniupnpd.leases
	test -f /var/run/miniupnpd.leases6 && test ! -s /var/run/miniupnpd.leases6
	ubus call luci.upnp get_status
	ubus call service list '{"name":"miniupnpd"}'
	cat /proc/sys/kernel/random/boot_id
	/usr/sbin/miniupnpd --version
	;;
cleanup)
	[ -d "$TASK_BACKUP" ] || exit 0
	/etc/init.d/miniupnpd stop
	cp "$TASK_BACKUP/network" "$TASK_BACKUP/upnpd" /etc/config/
	cp "$TASK_BACKUP/leases" /var/run/miniupnpd.leases
	cp "$TASK_BACKUP/leases6" /var/run/miniupnpd.leases6
	/etc/init.d/network reload
	sleep 2
	fw4 reload
	/etc/init.d/miniupnpd start
	mv "$TASK_BACKUP" "/root/upnp-boot-backup-$(date +%s)"
	;;
*) echo 'usage: boot-smoke.sh setup|check|cleanup' >&2; exit 2 ;;
esac
