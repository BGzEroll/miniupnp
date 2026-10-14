#!/usr/bin/env python3
"""Real-kernel deletion/lease regression on lab.sh, with a test-only interposer."""
import json,os,sys,time,subprocess
import integration as t

output=sys.argv[1];results=[]
def case(name,fn):
    try:detail=fn();status='PASS'
    except Exception:
        import traceback
        detail=traceback.format_exc();status='FAIL'
    results.append({'name':name,'status':status,'detail':detail})
    open(output,'w').write(json.dumps(results,indent=2)+'\n')
    print(status,name,detail if status=='FAIL' else '',flush=True)
    if status=='FAIL':raise RuntimeError(name)
def mode(value=''):open('/tmp/upnp-delete-fault.mode','w').write(value)
def lease(family):return open('/tmp/upnp-lab.leases'+('6' if family==6 else '')).read()
def rpc(token):return json.loads(t.sh('ubus','call','luci.upnp','delete_rule',json.dumps({'token':token})))['result']
def rules():return (t.nft('upnp_prerouting'),t.nft('upnp_forward'))
def mapping(port=53100):t.ok(t.mapping(port,port+100,lease=600));return '4:TCP:'+str(port)
def pinhole(port=53200):return int(t.ok(t.pinhole(port=port,lease=600))['values']['UniqueID'])
original=t.pid();original_fds=len(os.listdir("/proc/"+original+"/fd"))
try:
    def normal4():
        token=mapping();assert rpc(token)=='OK';assert rules()==baseline
        assert '53100' not in lease(4);assert rpc(token)=='Not found'
        trace=open('/tmp/upnp-delete-fault.trace').read().splitlines()[-1]
        assert trace=='2 1 5',trace
        return {'one_transaction':True,'one_success_ack':True}
    baseline=rules();case('IPv4 deletion is atomic and repeated deletion is absent',normal4)
    def failure4(kind):
        token=mapping();before=rules();record=lease(4);mode(kind)
        assert rpc(token)=='Failed';assert rules()==before;assert lease(4)==record
        mode();assert rpc(token)=='OK';assert rules()==baseline
        # First-operation failure must not leave a success ACK for the next request.
        token=mapping(53101);assert rpc(token)=='OK'
        assert rules()==baseline
        return {'kernel_rules_preserved':True,'lease_preserved':True,'retry_and_next_request_ok':True}
    for kind in ('send','first','second','dump'):
        case('IPv4 '+kind+' failure preserves rules and lease',lambda kind=kind:failure4(kind));mode()
    def single4():
        token=mapping();rows=json.loads(t.sh('nft','-j','list','chain','inet','fw4','upnp_forward'))['nftables']
        handle=next(row['rule']['handle'] for row in rows if 'rule' in row)
        t.sh('nft','delete','rule','inet','fw4','upnp_forward','handle',str(handle))
        result=rpc(token)
        if result=='Failed':
            assert '53100' in lease(4)
            assert rpc(token)=='OK'
        else:assert result=='OK',result
        assert rules()==baseline
    case('IPv4 external filter removal permits a clean retry',single4)
    def normal6():
        uid=pinhole();assert rpc('6:'+str(uid))=='OK';assert rules()==baseline
        assert rpc('6:'+str(uid))=='Not found'
    case('IPv6 normal and already-absent deletion',normal6)
    def failure6(kind):
        uid=pinhole();before=rules();record=lease(6);mode(kind)
        if kind=='dump':t.pinop('GetPinholePackets',uid)
        assert rpc('6:'+str(uid))=='Failed';assert rules()==before;assert lease(6)==record
        mode();assert rpc('6:'+str(uid))=='OK';assert rules()==baseline
        uid=pinhole(53201);assert rpc('6:'+str(uid))=='OK';assert rules()==baseline
    for kind in ('send','first','dump'):
        case('IPv6 '+kind+' failure preserves rules and lease',lambda kind=kind:failure6(kind));mode()
    def race(token,family):
        for path in ('/tmp/upnp-delete-fault.ready','/tmp/upnp-delete-fault.resume'):
            try:os.unlink(path)
            except FileNotFoundError:pass
        mode('race'+str(family))
        process=subprocess.Popen(['ubus','call','luci.upnp','delete_rule',json.dumps({'token':token})],stdout=subprocess.PIPE)
        try:
            for _ in range(150):
                if os.path.exists('/tmp/upnp-delete-fault.ready'):break
                time.sleep(.01)
            assert os.path.exists('/tmp/upnp-delete-fault.ready')
            if family==4:t.sh('nft','flush','chain','inet','fw4','upnp_prerouting')
            t.sh('nft','flush','chain','inet','fw4','upnp_forward')
        finally:open('/tmp/upnp-delete-fault.resume','w').close()
        result=json.loads(process.communicate(timeout=4)[0])['result']
        assert result=='Not found',result
        assert rules()==baseline
    def race4():
        race(mapping(),4);assert '53100' not in lease(4)
    case('IPv4 concurrent rule flush is already absent',race4);mode()
    def race6():
        race('6:'+str(pinhole()),6);assert lease(6)==''
    case('IPv6 concurrent rule flush is already absent',race6);mode()
    def expiration():
        good=int(t.ok(t.pinhole(port=53210,lease=3))['values']['UniqueID'])
        bad=int(t.ok(t.pinhole(port=53211,lease=3))['values']['UniqueID'])
        entries=json.loads(t.sh('nft','-j','list','chain','inet','fw4','upnp_forward'))['nftables']
        handle=next(row['rule']['handle'] for row in entries if 'rule' in row and row['rule'].get('comment','').startswith('pinhole-'+str(bad)+' '))
        mode('handle:'+str(handle));time.sleep(4)
        rows=t.nft('upnp_forward')
        assert 'pinhole-'+str(good)+' ' not in rows
        assert 'pinhole-'+str(bad)+' ' in rows
        records=lease(6).splitlines()
        assert len(records)==1 and records[0].split(';')[5]==str(bad),records
        mode()
        for _ in range(40):
            t.client(op='soap',family=6,action='GetFirewallStatus',args={})
            if lease(6)=='':break
            time.sleep(.05)
        assert lease(6)=='';assert rules()==baseline
        return {'successful_expiration_removed':good,'failed_expiration_preserved':bad}
    case('Mixed IPv6 expiry preserves only the rule that failed deletion',expiration)
    def lost_ack(family):
        token=mapping() if family==4 else '6:'+str(pinhole())
        mode('ackloss')
        assert rpc(token)=='Not found'
        assert rules()==baseline;assert lease(family)==''
        mode()
    case('IPv4 lost kernel ACK confirms absence and removes lease',lambda:lost_ack(4))
    case('IPv6 lost kernel ACK confirms absence and removes lease',lambda:lost_ack(6))
    def external_rules():
        # Fill the daemon cache with an absent result, then emulate an external restore.
        assert rpc('4:TCP:53102')=='Not found'
        t.sh('nft','add','rule','inet','fw4','upnp_prerouting','iifname','"upnp-w"','ip','protocol','tcp','tcp','dport','53102','dnat','ip','to','198.18.0.2:53202')
        t.sh('nft','add','rule','inet','fw4','upnp_forward','iifname','"upnp-w"','ip','daddr','198.18.0.2','tcp','dport','53202','accept')
        assert rpc('4:TCP:53102')=='OK';assert rules()==baseline
    case('Deletion refreshes an absent cache after external rule recreation',external_rules)
    def resources():
        assert t.pid()==original
        final_fds=len(os.listdir('/proc/'+original+'/fd'))
        assert final_fds==original_fds,(original_fds,final_fds)
        return {'pid':original,'fd_before':original_fds,'fd_after':final_fds}
    case('Failures and socket replacement preserve PID and FD count',resources)
finally:
    mode();open(output+'.nft','w').write(t.sh('nft','list','ruleset'))
sys.exit(1 if any(row['status']!='PASS' for row in results) else 0)
