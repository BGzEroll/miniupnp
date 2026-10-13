#!/usr/bin/env python3
"""Rule coexistence on the real VM PassWall generator, without a proxy node."""
import json
import os
import subprocess
import sys
import time
import traceback
import integration as t

out=sys.argv[1];results=[];servers=[]
def case(name,fn):
    try:detail=fn();status='PASS'
    except Exception:detail=traceback.format_exc();status='FAIL'
    results.append({'name':name,'status':status,'detail':detail})
    open(out,'w').write(json.dumps(results,indent=2)+'\n');print(status,name,detail if status=='FAIL' else '',flush=True)
def signature(table):
    entries=json.loads(t.sh('nft','-j','list','table','inet',table))['nftables']
    rules=[]
    for e in entries:
        if 'rule' not in e:continue
        r=e['rule'];r.pop('handle',None)
        r['expr']=[x for x in r['expr'] if 'counter' not in x];rules.append(r)
    return json.dumps(rules,sort_keys=True)
def traffic():
    for proto,port in ((6,42000),(17,42001)):
        t.traffic(43000 if proto==6 else 43001,proto,4);t.traffic(port,proto,6)
for family in (4,6):
    for proto,port in ((6,42000),(17,42001)):
        servers.append(subprocess.Popen(['ip','netns','exec','upnp-lan','python3',t.SELF,'--echo',str(port),str(proto),str(family)]))
servers.append(subprocess.Popen(['ip','netns','exec','upnp-wan','python3',t.SELF,'--echo','45000','17','4']))
time.sleep(.4)
try:
    uids=[];original=t.pid()
    def create():
        before=signature('passwall')
        for proto,port,ext in ((6,42000,43000),(17,42001,43001)):
            t.ok(t.mapping(ext,port,'TCP' if proto==6 else 'UDP',lease=300))
            uids.append(int(t.ok(t.pinhole(port=port,proto=proto,lease=300))['values']['UniqueID']))
        traffic();assert signature('passwall')==before
        assert t.pid()==original
        return {'families':[4,6],'protocols':['TCP','UDP'],'passwall_rules_unchanged':True}
    case('PassWall rules coexist with dual-stack UPnP mappings',create)
    def public_wan():
        t.sh('ip','-4','addr','flush','dev','upnp-w','scope','global');t.sh('ip','addr','add','8.8.4.1/32','dev','upnp-w')
        t.sh('ip','route','replace','198.19.0.2/32','dev','upnp-w');t.WAN4='8.8.4.1';time.sleep(.4)
        traffic();assert t.pid()==original
        return {'isolated_public_WAN':'8.8.4.1','real_forwarding':True}
    case('Isolated public WAN inbound mappings bypass PassWall proxy policy',public_wan)
    def firewall_reload():
        before=signature('passwall')
        for _ in range(3):
            t.sh('fw4','reload');time.sleep(.6);traffic();assert signature('passwall')==before
            assert t.nft('upnp_prerouting').count('dnat ip to')==2
        assert t.pid()==original
    case('Repeated fw4 reload preserves both tables and UPnP IDs',firewall_reload)
    def passwall_reload():
        before=signature('fw4')
        for _ in range(2):
            t.sh('sh','/tmp/passwall-driver.sh','stop');traffic();assert signature('fw4')==before
            t.sh('sh','/tmp/passwall-driver.sh','start');traffic();assert signature('fw4')==before
        assert t.pid()==original
    case('PassWall stop and rule reload leave fw4 UPnP rules intact',passwall_reload)
    def active_policy():
        t.sh('ip','-n','upnp-wan','addr','add','9.9.9.2/32','dev','upnp-c-wan')
        t.sh('ip','route','add','9.9.9.2/32','dev','upnp-w')
        def packets():
            rows=json.loads(t.sh('nft','-j','list','chain','inet','passwall','PSW_PROXY_UDP4'))['nftables']
            return sum(e['counter']['packets'] for row in rows if 'rule' in row for e in row['rule']['expr'] if 'counter' in e)
        before=packets()
        assert not t.client(op='probe',host='9.9.9.2',port=45000,proto=17)['forwarded']
        assert packets()>before
        traffic()
        t.sh('sh','/tmp/passwall-driver.sh','stop')
        return {'proxy_policy_intercepts_synthetic_outbound':True,'no_external_packets':True}
    case('Proxy hooks are active while mapped inbound traffic stays direct',active_policy)
    def cleanup_mappings():
        t.ok(t.delete(43000,'TCP'));t.ok(t.delete(43001,'UDP'))
        for uid in uids:t.ok(t.pinop('DeletePinhole',uid))
        assert 'dnat ip to' not in t.nft('upnp_prerouting');assert 'pinhole-' not in t.nft('upnp_forward')
        assert t.pid()==original
    case('Deleting all mappings leaves no UPnP residual rules',cleanup_mappings)
finally:
    for p in servers:p.terminate()
    for p in servers:p.wait(timeout=3)
    open(os.path.splitext(out)[0]+'.nft','w').write(t.sh('nft','list','ruleset'))
sys.exit(1 if any(x['status']!='PASS' for x in results) else 0)
