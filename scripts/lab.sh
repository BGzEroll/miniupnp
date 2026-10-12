#!/bin/sh
# Isolated test devices inside the authorized VM. No physical NIC membership.
set -eu
case "${1:-}" in
setup)
	[ ! -e /root/upnp-lab-backup ] || { echo 'Lab already active; run cleanup first' >&2; exit 1; }
	# On this VM DHCPv6 completes after SSH becomes available. Its initial
	# fw4 reload must finish before unrelated isolated mapping assertions.
	for iface in wan wan6; do
		tries=0
		while [ "$(ubus call "network.interface.$iface" status 2>/dev/null | jsonfilter -e '@.pending')" = true ]; do
			tries=$((tries + 1))
			[ "$tries" -le 30 ] || { echo "VM $iface protocol setup still pending" >&2; exit 1; }
			sleep 1
		done
	done
	mkdir /root/upnp-lab-backup
	cp /etc/config/network /etc/config/firewall /etc/config/upnpd /root/upnp-lab-backup/
	/etc/init.d/miniupnpd stop
	uci -q batch <<'EOT'
set firewall.upnplan=zone
set firewall.upnplan.name='upnplan'
add_list firewall.upnplan.device='upnp-l'
set firewall.upnplan.input='ACCEPT'
set firewall.upnplan.output='ACCEPT'
set firewall.upnplan.forward='ACCEPT'
set firewall.upnpwan=zone
set firewall.upnpwan.name='upnpwan'
add_list firewall.upnpwan.device='upnp-w'
set firewall.upnpwan.input='REJECT'
set firewall.upnpwan.output='ACCEPT'
set firewall.upnpwan.forward='REJECT'
set firewall.upnpwan.masq='1'
set firewall.upnpnd=rule
set firewall.upnpnd.name='Lab IPv6 input and neighbor discovery'
set firewall.upnpnd.src='upnpwan'
set firewall.upnpnd.family='ipv6'
set firewall.upnpnd.proto='icmp'
set firewall.upnpnd.target='ACCEPT'
set firewall.upnpout=forwarding
set firewall.upnpout.src='upnplan'
set firewall.upnpout.dest='upnpwan'
set firewall.@defaults[0].flow_offloading='0'
set firewall.@defaults[0].flow_offloading_hw='0'
set upnpd.config.enabled='1'
set upnpd.config.external_iface='upnpwan'
set upnpd.config.external_iface6='upnpwan'
set upnpd.config.internal_iface='upnplan'
set upnpd.config.upnp_lease_file='/tmp/upnp-lab.leases'
set upnpd.config.upnp_lease_file6='/tmp/upnp-lab.leases6'
set upnpd.config.config_file='/tmp/upnp-lab.conf'
set upnpd.config.igdv1='0'
set upnpd.config.ipv6_disable='0'
commit firewall
commit upnpd
EOT
	# No netifd reload: raw lab devices stay independent of physical interfaces.
	for side in l w; do
		ip link add "upnp-l2$side" type bridge
		ip link set "upnp-l2$side" up
		ip link add link "upnp-l2$side" name "upnp-$side" type macvlan mode bridge
		ip link set "upnp-$side" up
	done
	ip addr add 198.18.0.1/24 dev upnp-l
	ip addr add 198.19.0.1/24 dev upnp-w
	ip route add 198.19.0.2/32 dev upnp-w
	ip -6 addr add fd42:100::1/64 dev upnp-l nodad
	ip -6 addr add fd42:200::1/64 dev upnp-w nodad
	for client in lan other wan; do
		ip netns add "upnp-$client"
		side=l; octet=2; prefix=100; net=18
		[ "$client" != other ] || octet=3
		[ "$client" != wan ] || { side=w; prefix=200; net=19; }
		ip link add link "upnp-l2$side" name "upnp-c-$client" type macvlan mode bridge
		ip link set "upnp-c-$client" netns "upnp-$client"
		ip -n "upnp-$client" link set lo up
		ip -n "upnp-$client" link set "upnp-c-$client" up
		ip -n "upnp-$client" addr add "198.$net.0.$octet/24" dev "upnp-c-$client"
		ip -n "upnp-$client" -6 addr add "fd42:$prefix::$octet/64" dev "upnp-c-$client" nodad
		ip -n "upnp-$client" route add default via "198.$net.0.1"
		[ "$client" != wan ] || ip -n upnp-wan route replace default dev upnp-c-wan
		ip -n "upnp-$client" -6 route add default via "fd42:$prefix::1"
	done
	sed -e 's/^ext_ifname=.*/ext_ifname=upnp-w/' \
	    -e 's/^ext_ifname6=.*/ext_ifname6=upnp-w/' \
	    -e 's/^listening_ip=.*/listening_ip=upnp-l/' \
	    -e 's|^lease_file=.*|lease_file=/tmp/upnp-lab.leases|' \
	    -e 's|^lease_file6=.*|lease_file6=/tmp/upnp-lab.leases6|' \
	    /var/etc/miniupnpd.conf > /tmp/upnp-lab.conf
	: > /tmp/upnp-lab.leases
	: > /tmp/upnp-lab.leases6
	fw4 reload
	/etc/init.d/miniupnpd enable
	/etc/init.d/miniupnpd start
	;;
cleanup)
	[ -d /root/upnp-lab-backup ] || exit 0
	/etc/init.d/miniupnpd stop
	cp /root/upnp-lab-backup/network /root/upnp-lab-backup/firewall /root/upnp-lab-backup/upnpd /etc/config/
	/etc/init.d/network reload
	sleep 2
	for client in lan other wan; do ip netns del "upnp-$client" 2>/dev/null || :; done
	for side in l w; do
		ip link del "upnp-$side" 2>/dev/null || :
		ip link del "upnp-l2$side" 2>/dev/null || :
	done
	fw4 reload
	/etc/init.d/miniupnpd start
	# Keep previous backups as evidence; allow another repeatable run.
	mv /root/upnp-lab-backup "/root/upnp-lab-backup-$(date +%s)"
	;;
*) echo 'usage: lab.sh setup|cleanup' >&2; exit 2 ;;
esac
