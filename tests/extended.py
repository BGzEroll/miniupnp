#!/usr/bin/env python3
"""Slower lease, multi-client, remote filter and persistence checks for lab.sh."""
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback
spec=importlib.util.spec_from_file_location('integration',os.path.join(os.path.dirname(__file__),'integration.py'))
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
results=[]
output=sys.argv[1] if len(sys.argv)>1 else '/tmp/upnp-extended.json'

def case(name,fn):
    start=time.time()
    try:detail=fn();status='PASS'
    except Exception:detail=traceback.format_exc();status='FAIL'
    results.append({'name':name,'status':status,'seconds':round(time.time()-start,2),'detail':detail})
    print(status,name,detail if status=='FAIL' else '',flush=True)
    with open(output,'w') as f:json.dump(results,f,indent=2)

servers=[]
for family in (4,6):
    for proto in (6,17):
        for port in (42000,42001):servers.append(subprocess.Popen(['ip','netns','exec','upnp-lan','python3',t.SELF,'--echo',str(port),str(proto),str(family)]))
time.sleep(.5)
try:
    def persistence():
        original=t.pid()
        for family in (4,6):t.ok(t.client(op='pcp',family=family,proto=17,iport=42001,eport=43001 if family==4 else 42001,lifetime=180))
        before6=open('/tmp/upnp-lab.leases6').read();assert 'PCP MAP ' in before6
        t.sh('fw4','reload');time.sleep(.5);assert t.pid()==original
        t.sh('/etc/init.d/miniupnpd','restart');time.sleep(.7)
        for family in (4,6):
            t.traffic(43001 if family==4 else 42001,17,family)
            t.ok(t.client(op='pcp',family=family,proto=17,iport=42001,eport=43001 if family==4 else 42001,lifetime=240))
            t.ok(t.client(op='pcp',family=family,proto=17,iport=42001,eport=43001 if family==4 else 42001,lifetime=0))
        return {'nonce_and_both_lease_files':True}
    case('PCP nonce preservation after fw4 reload and daemon restart',persistence)
    def ipv6_prefix():
        original=t.pid();uid=int(t.ok(t.pinhole())['values']['UniqueID'])
        try:
            t.sh('ip','-6','addr','flush','dev','upnp-w','scope','global')
            t.sh('ip','-6','addr','add','fd42:201::1/64','dev','upnp-w','nodad')
            t.sh('ip','-n','upnp-wan','-6','addr','flush','dev','upnp-c-wan','scope','global')
            t.sh('ip','-n','upnp-wan','-6','addr','add','fd42:201::2/64','dev','upnp-c-wan','nodad')
            t.sh('ip','-n','upnp-wan','-6','route','replace','default','via','fd42:201::1')
            time.sleep(.4);t.traffic(42000,6,6);assert t.pid()==original
        finally:
            t.sh('ip','-6','addr','flush','dev','upnp-w','scope','global')
            t.sh('ip','-6','addr','add','fd42:200::1/64','dev','upnp-w','nodad')
            t.sh('ip','-n','upnp-wan','-6','addr','flush','dev','upnp-c-wan','scope','global')
            t.sh('ip','-n','upnp-wan','-6','addr','add','fd42:200::2/64','dev','upnp-c-wan','nodad')
            t.sh('ip','-n','upnp-wan','-6','route','replace','default','via','fd42:200::1')
        time.sleep(.4);t.traffic(42000,6,6);t.ok(t.pinop('DeletePinhole',uid))
        return {'real_forward_across_WAN_prefix_change':True,'pid_unchanged':True}
    case('IPv6 WAN ULA prefix change actual forwarding',ipv6_prefix)
    def remote_filter():
        uid=int(t.ok(t.pinhole(port=42000,proto=17,remote='fd42:200::3'))['values']['UniqueID'])
        t.traffic(42000,17,6,False);t.ok(t.pinop('DeletePinhole',uid))
        uid=int(t.ok(t.pinhole(port=42000,proto=17,remote='fd42:200::2'))['values']['UniqueID'])
        t.traffic(42000,17,6);t.ok(t.pinop('DeletePinhole',uid))
        return {'source_filter_enforced':True}
    case('IPv6 remote host restriction',remote_filter)
    def independent_leases():
        a=int(t.ok(t.pinhole(port=42000,proto=6,lease=180))['values']['UniqueID'])
        b=int(t.ok(t.pinhole(port=42001,proto=17,lease=180))['values']['UniqueID'])
        t.ok(t.pinop('UpdatePinhole',a,NewLeaseTime=240))
        lines=open('/tmp/upnp-lab.leases6').read().splitlines();ids=[int(x.split(';')[5]) for x in lines]
        assert set(ids)=={a,b},(a,b,lines)
        t.sh('/etc/init.d/miniupnpd','restart');time.sleep(.7)
        t.traffic(42000,6,6);t.traffic(42001,17,6)
        t.ok(t.pinop('DeletePinhole',a));t.ok(t.pinop('DeletePinhole',b))
        return {'IDs':ids,'other_lease_unchanged':True}
    case('Renew one IPv6 lease preserves other IDs and records',independent_leases)
    def long_lease_record():
        uid=int(t.ok(t.pinhole(port=42000,proto=6,lease=180))['values']['UniqueID'])
        path='/tmp/upnp-lab.leases6'
        fields=open(path).read().strip().split(';')
        # Legacy files may contain a long description, even if nft comments
        # are now bounded. It must not split into bogus follow-up records.
        fields[-1]='legacy-description-'+'x'*180
        record=';'.join(fields)+'\n'
        assert len(record)>128
        with open(path,'w') as f:f.write(record)
        t.sh('/etc/init.d/miniupnpd','restart');time.sleep(.7)
        t.traffic(42000,6,6)
        rows=open(path).read().splitlines()
        assert len(rows)==1 and rows[0].split(';')[5]==str(uid),rows
        assert rows[0].split(';')[-1]==fields[-1],rows
        t.ok(t.pinop('UpdatePinhole',uid,NewLeaseTime=240))
        assert len(open(path).read().splitlines())==1
        t.ok(t.pinop('DeletePinhole',uid))
        assert not open(path).read().strip()
        return {'record_bytes':len(record),'ID':uid,'forward_renew_delete':True}
    case('Long IPv6 lease record restore renewal deletion',long_lease_record)
    def many_clients():
        procs=[]
        for ns,start in [('lan',45000),('other',45100)]:
            procs.append(subprocess.Popen(['ip','netns','exec','upnp-'+ns,'python3',t.SELF,'--client',json.dumps({'op':'stress','count':150,'start':start})],stdout=subprocess.PIPE,stderr=subprocess.PIPE))
        for p in procs:
            stdout,stderr=p.communicate(timeout=20);assert p.returncode==0,stderr.decode()
        assert 'dnat ip to' not in t.nft('upnp_prerouting')
        return {'clients':2,'cycles':300}
    case('Concurrent clients mixed TCP/UDP bounded workload',many_clients)
    def short_pmp_expiry():
        r=t.ok(t.client(op='pmp',proto=17,iport=42000,eport=43000,lifetime=3));assert r['lifetime']==3,r
        t.traffic(43000,17);time.sleep(4);t.traffic(43000,17,expected=False)
    case('NAT-PMP granted lease expiry',short_pmp_expiry)
    def pcp_expiry():
        lifetimes=[]
        for family in (4,6):
            r=t.ok(t.client(op='pcp',family=family,proto=17,iport=42000,eport=43000 if family==4 else 42000,lifetime=1));assert r['lifetime']>=120,r;lifetimes.append(r['lifetime'])
            t.traffic(43000 if family==4 else 42000,17,family)
        time.sleep(max(lifetimes)+2)
        for family in (4,6):t.traffic(43000 if family==4 else 42000,17,family,False)
        return {'actual_granted_lifetimes':lifetimes}
    case('PCP IPv4 IPv6 minimum granted lifetime and actual expiry',pcp_expiry)
    def no_wan_logs():
        original=t.pid()
        t.sh('ip','-4','addr','flush','dev','upnp-w','scope','global');time.sleep(.3)
        before=t.sh('logread','-e','miniupnpd')
        for i in range(25):
            assert t.client(op='pmp',opcode=0)['error']!=0
            assert t.mapping()['error']!=0
            r=t.client(op='pcp');assert r['error']==7,r
            t.sh('ubus','call','service','signal','{"name":"miniupnpd","signal":10}')
        time.sleep(2);assert not t.added_logs(before,t.sh('logread','-e','miniupnpd')),t.added_logs(before,t.sh('logread','-e','miniupnpd'))
        t.sh('ip','addr','add','198.19.0.1/24','dev','upnp-w');time.sleep(.3)
        assert t.pid()==original;t.ok(t.mapping());t.traffic(43000);t.ok(t.delete())
        return {'repeated_requests_and_signals':25,'repeated_logs':0}
    case('No IPv4 address repeated requests do not log flood',no_wan_logs)
finally:
    for p in servers:p.terminate()
    for p in servers:p.wait(timeout=3)
sys.exit(1 if any(x['status']=='FAIL' for x in results) else 0)
