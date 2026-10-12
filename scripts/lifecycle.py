#!/usr/bin/env python3
"""Generated UCI configuration, protocol switches and WAN device recreation."""
import importlib.util,json,os,subprocess,sys,time
import traceback
spec=importlib.util.spec_from_file_location('integration',os.path.join(os.path.dirname(__file__),'integration.py'));t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
results=[];out=sys.argv[1] if len(sys.argv)>1 else '/tmp/upnp-lifecycle.json'
def case(name,fn):
    start=time.time()
    try:detail=fn();status='PASS'
    except Exception:detail=traceback.format_exc();status='FAIL'
    results.append({'name':name,'status':status,'seconds':round(time.time()-start,2),'detail':detail});print(status,name,detail if status=='FAIL' else '',flush=True)
    with open(out,'w') as f:json.dump(results,f,indent=2)
def setting(**values):
    try:old_pid=t.pid()
    except RuntimeError:old_pid=''
    for key,value in values.items():t.sh('uci','set','upnpd.config.'+key+'='+str(value))
    t.sh('uci','commit','upnpd');t.sh('/etc/init.d/miniupnpd','reload')
    enabled=t.sh('uci','get','upnpd.config.enabled').strip()=='1'
    upnp=t.sh('uci','get','upnpd.config.enable_upnp').strip()=='1'
    natpmp=t.sh('uci','get','upnpd.config.enable_natpmp').strip()=='1'
    deadline=time.monotonic()+8
    while True:
        try:
            if not enabled:
                try:t.pid();raise AssertionError('still running')
                except RuntimeError:break
            assert t.pid()!=old_pid
            if upnp:t.ok(t.client(op='http'))
            elif natpmp:t.ok(t.client(op='pmp',opcode=0))
            break
        except (RuntimeError,AssertionError):
            if time.monotonic()>deadline:raise
            time.sleep(.15)
servers=[]
for family in (4,6):
    for proto in (6,17):
        for port in (42000,42001):servers.append(subprocess.Popen(['ip','netns','exec','upnp-lan','python3',t.SELF,'--echo',str(port),str(proto),str(family)]))
time.sleep(.3)
try:
    def recreate():
        original=t.pid();t.ok(t.mapping(lease=180));uid=int(t.ok(t.pinhole(lease=180))['values']['UniqueID'])
        old_index=int(open('/sys/class/net/upnp-w/ifindex').read());mac=open('/sys/class/net/upnp-w/address').read().strip()
        t.sh('ip','link','del','upnp-w');time.sleep(.3)
        t.sh('ip','link','add','link','upnp-l2w','name','upnp-w','address',mac,'type','macvlan','mode','bridge');t.sh('ip','link','set','upnp-w','up')
        t.sh('ip','addr','add','198.19.0.1/24','dev','upnp-w');t.sh('ip','-6','addr','add','fd42:200::1/64','dev','upnp-w','nodad')
        t.sh('/etc/init.d/miniupnpd','reload');time.sleep(.4)
        new_index=int(open('/sys/class/net/upnp-w/ifindex').read());assert new_index!=old_index
        end=time.monotonic()+5
        while True:
            try:t.traffic(43000);t.traffic(42000,6,6);break
            except AssertionError:
                if time.monotonic()>end:raise
                time.sleep(.3)
        assert t.pid()==original;t.ok(t.delete());t.ok(t.pinop('DeletePinhole',uid))
        return {'old_ifindex':old_index,'new_ifindex':new_index,'pid_unchanged':True,'both_families_forwarded':True}
    case('Same WAN name new ifindex preserves IPv4 IPv6 forwarding',recreate)
    def unnumbered_ipv6():
        ll=t.sh('ip','-6','addr','show','dev','upnp-w','scope','link').split('inet6 ')[1].split('/')[0]
        t.sh('ip','-6','addr','flush','dev','upnp-w','scope','global')
        t.sh('ip','-6','route','replace','fd42:200::/64','dev','upnp-w')
        t.sh('ip','-n','upnp-wan','-6','route','replace','default','via',ll,'dev','upnp-c-wan')
        try:
            uid=int(t.ok(t.pinhole())['values']['UniqueID']);t.traffic(42000,6,6);t.ok(t.pinop('DeletePinhole',uid))
        finally:
            t.sh('ip','-6','addr','add','fd42:200::1/64','dev','upnp-w','nodad')
            t.sh('ip','-n','upnp-wan','-6','route','replace','default','via','fd42:200::1','dev','upnp-c-wan')
        return {'WAN_link_local_only':True,'LAN_ULA_forwarded':True}
    case('IPv6 routed WAN with only link-local address',unnumbered_ipv6)

    # Logical aliases are only staged in UCI, not applied to netifd or any physical NIC.
    for interface,device in [('upnplan','upnp-l'),('upnpwan','upnp-w')]:
        t.sh('uci','set','network.'+interface+'=interface');t.sh('uci','set','network.'+interface+'.device='+device)
    t.sh('uci','-q','delete','upnpd.config.config_file')
    setting(enabled=1,enable_upnp=1,enable_natpmp=1,ipv6_disable=0)
    def enabled_event(value):
        t.sh('uci','set','upnpd.config.enabled='+str(value));t.sh('uci','commit','upnpd')
        # Match LuCI's config event without manually invoking init reload.
        t.sh('ubus','call','service','event',json.dumps({'type':'config.change','data':{'package':'upnpd'}}))
        deadline=time.monotonic()+8
        while True:
            try:
                if value:t.ok(t.client(op='http'))
                else:
                    try:t.pid();raise AssertionError('still running')
                    except RuntimeError:pass
                    assert 'miniupnpd' in json.loads(t.sh('ubus','call','service','list','{"name":"miniupnpd"}'))
                break
            except (RuntimeError,AssertionError):
                if time.monotonic()>deadline:raise
                time.sleep(.15)
    def disable_enable():
        t.ok(t.mapping(lease=300));uid=int(t.ok(t.pinhole(lease=300))['values']['UniqueID'])
        enabled_event(0)
        try:t.pid();raise AssertionError('daemon still running')
        except RuntimeError:pass
        assert 'dnat ip to' not in t.nft('upnp_prerouting');assert 'accept' not in t.nft('upnp_forward')
        enabled_event(1);t.traffic(43000);t.traffic(42000,6,6);t.ok(t.delete());t.ok(t.pinop('DeletePinhole',uid))
    case('UCI enable off clears rules on restores leases',disable_enable)
    def ipv6_switch():
        t.ok(t.mapping(lease=180));uid=int(t.ok(t.pinhole(lease=180))['values']['UniqueID'])
        setting(ipv6_disable=1);t.traffic(43000);assert 'pinhole-' not in t.nft('upnp_forward')
        setting(ipv6_disable=0);t.traffic(42000,6,6);t.ok(t.pinop('GetPinholePackets',uid));t.ok(t.delete());t.ok(t.pinop('DeletePinhole',uid))
    case('UCI IPv6 off has no pinholes on preserves valid ID',ipv6_switch)
    def only_pcp():
        setting(enable_upnp=0)
        try:t.client(op='http');raise AssertionError('UPnP HTTP remains active')
        except RuntimeError:pass
        for family in (4,6):
            r=t.ok(t.client(op='pcp',family=family,iport=42000,eport=43000 if family==4 else 42000));t.traffic(r['eport'],6,family)
            t.ok(t.client(op='pcp',family=family,iport=42000,eport=r['eport'],lifetime=0))
        setting(enable_upnp=1)
    case('UCI UPnP off keeps PCP IPv4 IPv6 operational',only_pcp)
    def only_soap():
        setting(enable_natpmp=0)
        try:t.client(op='pmp',opcode=0);raise AssertionError('NAT-PMP remains active')
        except RuntimeError:pass
        t.ok(t.mapping());uid=int(t.ok(t.pinhole())['values']['UniqueID']);t.traffic(43000);t.traffic(42000,6,6);t.ok(t.delete());t.ok(t.pinop('DeletePinhole',uid))
        setting(enable_natpmp=1)
    case('UCI PCP NAT-PMP off keeps SOAP dual stack operational',only_soap)
    def unsafe_targets():
        setting(secure_mode=0)
        for ip in ('0.0.0.0','127.0.0.1','224.0.0.1','192.0.2.1','198.18.0.255','198.18.0.0'):
            r=t.mapping(ip=ip);assert r['error']!=0,(ip,r)
        setting(secure_mode=1)
    case('Illegal non-LAN network broadcast targets denied even without secure mode',unsafe_targets)
    def lan_prefix():
        uid=int(t.ok(t.pinhole())['values']['UniqueID'])
        try:
            t.sh('ip','-6','addr','flush','dev','upnp-l','scope','global');t.sh('ip','-6','addr','add','fd42:101::1/64','dev','upnp-l','nodad')
            # Simulate the legitimate config update/restart for changed LAN addresses.
            t.sh('/etc/init.d/miniupnpd','restart');time.sleep(.7)
            assert 'fd42:100::2' not in t.nft('upnp_forward')
            assert 'fd42:100::2' not in open('/tmp/upnp-lab.leases6').read()
        finally:
            t.sh('ip','-6','addr','flush','dev','upnp-l','scope','global');t.sh('ip','-6','addr','add','fd42:100::1/64','dev','upnp-l','nodad');t.sh('/etc/init.d/miniupnpd','restart');time.sleep(.7)
        return {'old_prefix_lease_not_resurrected':True}
    case('Removed LAN IPv6 prefix lease not restored',lan_prefix)
finally:
    t.sh('uci','revert','network')
    # Restore the lab config entrance so subsequent scripts use the same topology.
    setting(config_file='/tmp/upnp-lab.conf',enabled=1,enable_upnp=1,enable_natpmp=1,ipv6_disable=0,secure_mode=1)
    for p in servers:p.terminate()
    for p in servers:p.wait(timeout=3)
sys.exit(1 if any(x['status']=='FAIL' for x in results) else 0)
