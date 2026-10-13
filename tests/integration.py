#!/usr/bin/env python3
"""Real protocol and TCP/UDP forwarding regression on tests/lab.sh topology.
Run on the authorized VM. Python is a test dependency, never a daemon dependency.
"""
import json
import os
import re
import socket
import struct
import subprocess
import sys
import time
import traceback

LAN4='198.18.0.2'; LAN6='fd42:100::2'
GW4='198.18.0.1'; GW6='fd42:100::1'
WAN4='198.19.0.1'
SELF=os.path.abspath(__file__)


def http(host=GW4, method='GET', path='/rootDesc.xml', body='', headers=None):
    family=socket.AF_INET6 if ':' in host else socket.AF_INET
    s=socket.socket(family,socket.SOCK_STREAM);s.settimeout(2)
    s.connect((host,5000))
    data=body.encode(); h={'Host':('['+host+']' if family==socket.AF_INET6 else host),'Connection':'close','Content-Length':str(len(data))}
    h.update(headers or {})
    wire=f'{method} {path} HTTP/1.1\r\n'+''.join(f'{k}: {v}\r\n' for k,v in h.items())+'\r\n'
    s.sendall(wire.encode()+data);r=b''
    while True:
        chunk=s.recv(65536)
        if not chunk:break
        r+=chunk
    s.close();head,body=r.split(b'\r\n\r\n',1)
    return {'status':int(head.split()[1]),'body':body.decode(errors='replace')}


def soap(family, action, args, version=2):
    ipv6=family==6
    service='WANIPv6FirewallControl:1' if ipv6 else f'WANIPConnection:{version}'
    ns='urn:schemas-upnp-org:service:'+service
    escape=lambda v:str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    body='<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'+f'<u:{action} xmlns:u="{ns}">'+''.join(f'<{k}>{escape(v)}</{k}>' for k,v in args.items())+f'</u:{action}></s:Body></s:Envelope>'
    r=http(GW6 if ipv6 else GW4,'POST','/ctl/IP6FCtl' if ipv6 else '/ctl/IPConn',body,{'SOAPAction':f'"{ns}#{action}"','Content-Type':'text/xml; charset="utf-8"'})
    r['values']=dict(re.findall(r'<([A-Za-z][A-Za-z0-9]*)>([^<]*)</\1>',r['body']))
    r['error']=int(r['values'].get('errorCode','0'))
    return r


def pmp(proto=6,iport=42000,eport=43000,lifetime=60,opcode=None):
    op=opcode if opcode is not None else (2 if proto==6 else 1)
    req=struct.pack('!BB',0,op) if op==0 else struct.pack('!BBHHHI',0,op,0,iport,eport,lifetime)
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(2)
    s.sendto(req,(GW4,5351));r=s.recv(1500);s.close()
    result={'version':r[0],'opcode':r[1],'error':struct.unpack('!H',r[2:4])[0]}
    if op==0 and len(r)>=12:result['address']=socket.inet_ntop(socket.AF_INET,r[8:12])
    if op!=0 and len(r)>=16:result.update(zip(['iport','eport','lifetime'],struct.unpack('!HHI',r[8:16])))
    return result


def pcp(family=4,proto=6,iport=42000,eport=43000,lifetime=120,nonce='0102030405060708090a0b0c',client=None,options=''):
    address=client or (LAN6 if family==6 else '::ffff:'+LAN4)
    req=struct.pack('!BBHI',2,1,0,lifetime)+socket.inet_pton(socket.AF_INET6,address)
    req+=bytes.fromhex(nonce)+struct.pack('!B3xHH',proto,iport,eport)+bytes(16)+bytes.fromhex(options)
    s=socket.socket(socket.AF_INET6 if family==6 else socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(2)
    s.sendto(req,(GW6 if family==6 else GW4,5351));r=s.recv(1500);s.close()
    result={'version':r[0],'opcode':r[1],'error':r[3],'lifetime':struct.unpack('!I',r[4:8])[0]}
    if len(r)>=60:result.update({'nonce':r[24:36].hex(),'proto':r[36],'iport':struct.unpack('!H',r[40:42])[0],'eport':struct.unpack('!H',r[42:44])[0],'address':socket.inet_ntop(socket.AF_INET6,r[44:60])})
    return result


def probe(host,port,proto=6):
    s=socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET,socket.SOCK_STREAM if proto==6 else socket.SOCK_DGRAM);s.settimeout(.7)
    message=os.urandom(24)
    try:
        s.connect((host,port));s.sendall(message);ok=s.recv(1024)==message
    except OSError:ok=False
    finally:s.close()
    return {'forwarded':ok}


def echo(port,proto,family):
    s=socket.socket(socket.AF_INET6 if family==6 else socket.AF_INET,socket.SOCK_STREAM if proto==6 else socket.SOCK_DGRAM)
    if family==6:s.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
    s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('::' if family==6 else '0.0.0.0',port))
    if proto==6:
        s.listen(16)
        while True:
            c,_=s.accept();c.settimeout(1)
            try:c.sendall(c.recv(1024))
            except OSError:pass
            c.close()
    else:
        while True:
            data,peer=s.recvfrom(2048);s.sendto(data,peer)


def client_call(request):
    op=request.pop('op');return {'http':http,'soap':soap,'pmp':pmp,'pcp':pcp,'probe':probe,'stress':stress,'ssdp':ssdp}[op](**request)


def ssdp(st='urn:schemas-upnp-org:device:InternetGatewayDevice:2'):
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(2)
    request=f'M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\nMAN:"ssdp:discover"\r\nMX:1\r\nST:{st}\r\n\r\n'
    # Unicast exercises discovery response without leaving the isolated segment.
    s.sendto(request.encode(),(GW4,1900));r=s.recv(4096).decode();s.close()
    return {'response':r}


def stress(count=100,start=45000):
    for i in range(count):
        proto=6 if i%2 else 17;eport=start+i%50;iport=eport+1000
        r=pmp(proto,iport,eport,120);assert r['error']==0,r
        r=pmp(proto,iport,eport,0);assert r['error']==0,r
        time.sleep(.02)
    return {'cycles':count}


def sh(*args):
    try:return subprocess.check_output(args,stderr=subprocess.STDOUT).decode()
    except subprocess.CalledProcessError as e:raise RuntimeError(str(args)+': '+e.output.decode(errors='replace')[-1600:]) from e


def client(ns='lan',**req):
    return json.loads(sh('ip','netns','exec','upnp-'+ns,'python3',SELF,'--client',json.dumps(req)))


def mapping(eport=43000,iport=42000,proto='TCP',lease=60,ip=LAN4,version=2,ns='lan'):
    return client(ns,op='soap',family=4,version=version,action='AddPortMapping',args={'NewRemoteHost':'','NewExternalPort':eport,'NewProtocol':proto,'NewInternalPort':iport,'NewInternalClient':ip,'NewEnabled':1,'NewPortMappingDescription':'upnp-lab','NewLeaseDuration':lease})


def delete(eport=43000,proto='TCP'):
    return client(op='soap',family=4,action='DeletePortMapping',args={'NewRemoteHost':'','NewExternalPort':eport,'NewProtocol':proto})


def pinhole(port=42000,proto=6,lease=60,ip=LAN6,remote='',rport=0):
    return client(op='soap',family=6,action='AddPinhole',args={'RemoteHost':remote,'RemotePort':rport,'InternalClient':ip,'InternalPort':port,'Protocol':proto,'LeaseTime':lease})


def pinop(action,uid,**extra):
    return client(op='soap',family=6,action=action,args={'UniqueID':uid,**extra})


def ok(r):
    assert r.get('error',0)==0,r
    if 'status' in r:assert r['status']==200,r
    return r


def traffic(port,proto=6,family=4,expected=True,host=None):
    r=client('wan',op='probe',host=host or (LAN6 if family==6 else WAN4),port=port,proto=proto)
    assert r['forwarded']==expected,(port,proto,family,r,expected)


def nft(chain):
    return sh('nft','list','chain','inet','fw4',chain)


def pid():return sh('pidof','miniupnpd').strip()


def added_logs(before,after):
    # logd may evict old records while unrelated services log; compare overlap.
    old=before.splitlines();new=after.splitlines()
    for size in range(min(len(old),len(new)),0,-1):
        if old[-size:]==new[:size]:return new[size:]
    return new



def run_suite(output):
    sh('ip','netns','exec','upnp-lan','true');sh('ip','netns','exec','upnp-wan','true')
    results=[];servers=[]
    def case(name,func):
        t=time.time()
        try:detail=func();status='PASS'
        except Exception:detail=traceback.format_exc();status='FAIL'
        results.append({'name':name,'status':status,'seconds':round(time.time()-t,3),'detail':detail})
        print(status,name,detail if status=='FAIL' else '',flush=True)
        with open(output,'w') as f:json.dump(results,f,indent=2)
    for family in (4,6):
        for proto in (6,17):
            for port in (42000,42001):
                servers.append(subprocess.Popen(['ip','netns','exec','upnp-lan','python3',SELF,'--echo',str(port),str(proto),str(family)]))
    time.sleep(.5)
    try:
        def description():
            r=ok(client(op='http'));assert 'InternetGatewayDevice:2' in r['body'];assert 'WANIPv6FirewallControl:1' in r['body']
            return {'igd2':True,'ipv6_service':True}
        case('IGDv2 description and IPv6 service',description)
        def compat():
            r=ok(client(op='http',headers={'User-Agent':'Microsoft-Windows/10.0 UPnP/1.0'}));assert 'InternetGatewayDevice:1' in r['body']
            ok(mapping(43000,42000,version=1));traffic(43000);ok(delete());return {'legacy_description':True,'v1_soap_to_v2':True}
        case('IGDv1 client compatibility',compat)
        case('SSDP IGDv1 search on IGDv2',lambda:client(op='ssdp',st='urn:schemas-upnp-org:device:InternetGatewayDevice:1'))
        case('SSDP IGDv2 search',lambda:client(op='ssdp'))
        for proto,pn in ((6,'TCP'),(17,'UDP')):
            def upnp_flow(proto=proto,pn=pn):
                for ep,ip in [(42000,42000),(43000,42001)]:
                    traffic(ep,proto,expected=False);ok(mapping(ep,ip,pn));traffic(ep,proto)
                    q=ok(client(op='soap',family=4,action='GetSpecificPortMappingEntry',args={'NewRemoteHost':'','NewExternalPort':ep,'NewProtocol':pn}));assert int(q['values']['NewInternalPort'])==ip,q
                    ok(mapping(ep,ip,pn,120));assert nft('upnp_prerouting').count('dnat ip to')==1
                    ct=sh('cat','/proc/net/nf_conntrack')
                    lines=[x for x in ct.splitlines() if 'src=198.19.0.2 ' in x and 'dst=198.19.0.1 ' in x and 'dport='+str(ep)+' ' in x and 'src='+LAN4+' ' in x and 'sport='+str(ip)+' ' in x]
                    assert lines,('missing conntrack DNAT evidence',ep,ip)
                    with open(output+'.conntrack','a') as f:f.write('\n'.join(lines)+'\n')
                    ok(delete(ep,pn));traffic(ep,proto,expected=False)
                return {'equal_and_unequal_ports':True,'renew_query_delete':True}
            case('UPnP '+pn+' DNAT and real forwarding',upnp_flow)
            def pmp_flow(proto=proto):
                ok(client(op='pmp',opcode=0));r=ok(client(op='pmp',proto=proto,iport=42000,eport=43000));assert r['eport']==43000 and r['iport']==42000,r
                traffic(43000,proto);ok(client(op='pmp',proto=proto,iport=42000,eport=43000,lifetime=120));ok(client(op='pmp',proto=proto,iport=42000,eport=43000,lifetime=0));traffic(43000,proto,expected=False)
            case('NAT-PMP '+pn+' forwarding renewal deletion',pmp_flow)
            def pcp_flow(proto=proto):
                r=ok(client(op='pcp',proto=proto,iport=42000,eport=43000));assert r['proto']==proto and r['eport']==43000,r
                traffic(43000,proto);ok(client(op='pcp',proto=proto,iport=42000,eport=43000,lifetime=240));ok(client(op='pcp',proto=proto,iport=42000,eport=43000,lifetime=0));traffic(43000,proto,expected=False)
            case('PCP IPv4 '+pn+' forwarding renewal deletion',pcp_flow)
            def pin_flow(proto=proto):
                traffic(42000,proto,6,False);r=ok(pinhole(proto=proto));uid=int(r['values']['UniqueID']);traffic(42000,proto,6)
                q=ok(pinop('GetPinholePackets',uid));assert int(q['values']['PinholePackets'])>0,q
                q=ok(pinop('CheckPinholeWorking',uid));assert int(q['values']['IsWorking'])==1,q
                ok(pinop('UpdatePinhole',uid,NewLeaseTime=120));r2=ok(pinhole(proto=proto));assert int(r2['values']['UniqueID'])==uid
                ok(pinop('DeletePinhole',uid));traffic(42000,proto,6,False)
            case('IPv6 SOAP '+pn+' pinhole real FORWARD and counters',pin_flow)
            def pcp6_flow(proto=proto):
                r=ok(client(op='pcp',family=6,proto=proto,iport=42000,eport=42000));assert r['eport']==42000 and r['address']==LAN6,r
                traffic(42000,proto,6);ok(client(op='pcp',family=6,proto=proto,iport=42000,eport=42000,lifetime=240));ok(client(op='pcp',family=6,proto=proto,iport=42000,eport=42000,lifetime=0));traffic(42000,proto,6,False)
            case('PCP IPv6 '+pn+' forwarding nonce renewal deletion',pcp6_flow)
        def security():
            assert mapping(ip='198.18.0.3')['error']!=0
            assert mapping(80,80)['error']!=0
            assert pinhole(ip='fd42:100::3')['error']!=0
            assert pinhole(port=80)['error']!=0
            assert pinhole(proto=1)['error']!=0
            assert pinhole(lease=0)['error']!=0
            r=client(op='pcp',client='::ffff:198.18.0.3');assert r['error']!=0,r
            assert client(op='soap',family=4,action='AddPortMapping',args={})['error']==402
        case('Secure mode ACL invalid SOAP PCP parameters',security)
        def boundaries():
            for val in (-1,65536,107536,'42000junk',''):
                r=mapping(iport=val);assert r['error']!=0,(val,r)
                r=pinhole(port=val);assert r['error']!=0,(val,r)
            for val in (-1,65536,108536,'43000junk'):
                r=mapping(eport=val);assert r['error']!=0,(val,r)
            assert mapping(lease=4294967296)['error']!=0
            assert pinop('GetPinholePackets',65534)['error']==704
            return {'port_boundaries':True,'no_such_id':True}
        case('Numeric bounds reject wraparound and nonexistent pinhole',boundaries)
        def nonce_security():
            for family in (4,6):
                ok(client(op='pcp',family=family,iport=42001,eport=43001 if family==4 else 42001))
                r=client(op='pcp',family=family,iport=42001,eport=43001 if family==4 else 42001,nonce='ffffffffffffffffffffffff',lifetime=0)
                assert r['error']!=0,(family,r)
                r=client(op='pcp',family=family,iport=42001,eport=43001 if family==4 else 42001,nonce='ffffffffffffffffffffffff',lifetime=120)
                assert r['error']!=0,(family,r)
                ok(client(op='pcp',family=family,iport=42001,eport=43001 if family==4 else 42001,lifetime=0))
            assert client(op='pcp',family=6,iport=80,eport=80)['error']!=0
        case('PCP IPv4 IPv6 nonce ownership and privileged IPv6 port',nonce_security)
        def luci_status():
            ok(mapping());uid=int(ok(pinhole())['values']['UniqueID']);original=pid()
            r=json.loads(sh('ubus','call','luci.upnp','get_status'))
            assert any(x['family']==4 and x['intport']==42000 and x['extport']==43000 for x in r['rules']),r
            assert any(x['family']==6 and x['num']=='6:'+str(uid) for x in r['rules']),r
            for token in ('4:TCP:43000','6:'+str(uid)):
                r=json.loads(sh('ubus','call','luci.upnp','delete_rule',json.dumps({'token':token})));assert r['result']=='OK',r
            traffic(43000,expected=False);traffic(42000,6,6,False);assert pid()==original
            r=json.loads(sh('ubus','call','luci.upnp','delete_rule',json.dumps({'token':'6:1; reboot'})));assert r['result']=='Bad request',r
            return {'both_families_listed':True,'delete_pid_unchanged':True}
        case('LuCI real IPv4 IPv6 status and safe deletion without restart',luci_status)

        def wan_control():
            try:r=client('wan',op='http',host=WAN4)
            except RuntimeError:return {'http_blocked':True}
            assert r['status']!=200,r
        case('WAN management HTTP blocked',wan_control)
        def conflict():
            ok(mapping());assert mapping(iport=42001,ip='198.18.0.3',ns='other')['error']!=0;ok(delete())
            ok(mapping());r=ok(client(op='pmp',proto=6,iport=42001,eport=43000));assert r['eport']!=43000,r
            ok(client(op='pmp',proto=6,iport=42001,eport=r['eport'],lifetime=0));ok(delete())
        case('Port conflicts and NAT-PMP alternative allocation',conflict)
        def igdv2_actions():
            r=ok(client(op='soap',family=4,action='AddAnyPortMapping',args={'NewRemoteHost':'','NewExternalPort':0,'NewProtocol':'TCP','NewInternalPort':42000,'NewInternalClient':LAN4,'NewEnabled':1,'NewPortMappingDescription':'igd2-any','NewLeaseDuration':120}))
            port=int(r['values']['NewReservedPort']);assert port>=1024,r;traffic(port)
            r=ok(client(op='soap',family=4,action='GetGenericPortMappingEntry',args={'NewPortMappingIndex':0}));assert int(r['values']['NewExternalPort'])==port,r
            r=ok(client(op='soap',family=6,action='GetFirewallStatus',args={}));assert r['values']['FirewallEnabled']=='1' and r['values']['InboundPinholeAllowed']=='1',r
            ok(delete(port))
        case('IGDv2 AddAnyPortMapping generic query and IPv6 firewall status',igdv2_actions)

        def expiration():
            ok(mapping(43000,42000,lease=3));uid=int(ok(pinhole(lease=3))['values']['UniqueID']);traffic(43000);traffic(42000,6,6)
            time.sleep(4);traffic(43000,expected=False);traffic(42000,6,6,False)
            assert pinop('GetPinholePackets',uid)['error']!=0
        case('IPv4 and IPv6 lease expiration closes new connections',expiration)
        def lifecycle():
            ok(mapping(43000,42000,lease=180));a=int(ok(pinhole(port=42001,lease=180))['values']['UniqueID']);ok(pinop('DeletePinhole',a))
            uid=int(ok(pinhole(lease=180))['values']['UniqueID'])
            original=pid()
            for i in range(3):
                sh('fw4','reload');time.sleep(.5);assert pid()==original
                traffic(43000);traffic(42000,6,6);ok(pinop('GetPinholePackets',uid))
                assert nft('upnp_prerouting').count('dnat ip to')==1
            for cmd in [('restart',),('stop','start')]:
                for action in cmd:sh('/etc/init.d/miniupnpd',action)
                time.sleep(.7);traffic(43000);traffic(42000,6,6);ok(pinop('GetPinholePackets',uid))
            ok(delete());ok(pinop('DeletePinhole',uid))
            return {'fw4_pid_unchanged':True,'pinhole_id_retained':uid}
        case('fw4 reload restart stop/start lease and ID recovery',lifecycle)
        def networks():
            global WAN4
            original=pid();states=[]
            # All addresses live on the isolated WAN only.
            for addr,label in [('8.8.4.1','public'),('10.23.0.1','RFC1918'),('100.64.1.1','CGNAT'),('198.19.0.1','benchmark unicast')]:
                sh('ip','-4','addr','flush','dev','upnp-w','scope','global');sh('ip','addr','add',addr+'/32','dev','upnp-w');WAN4=addr
                sh('ip','route','replace','198.19.0.2/32','dev','upnp-w')
                time.sleep(.3);r=ok(client(op='pmp',opcode=0));assert r['address']==addr,r
                ok(mapping());traffic(43000);ok(delete());assert pid()==original;states.append(label)
            sh('ip','-4','addr','flush','dev','upnp-w','scope','global');time.sleep(.3)
            r=client(op='pmp',opcode=0);assert r['error']!=0,r
            r=mapping();assert r['error']!=0,r
            assert 'dnat ip to' not in nft('upnp_prerouting')
            uid=int(ok(pinhole())['values']['UniqueID']);traffic(42000,6,6);ok(pinop('DeletePinhole',uid))
            sh('ip','addr','add','198.19.0.1/24','dev','upnp-w');WAN4='198.19.0.1';time.sleep(.4);ok(mapping());traffic(43000);ok(delete())
            # IPv6-only WAN: IPv6 pinhole still works; above IPv4 unavailable.
            sh('ip','-6','addr','flush','dev','upnp-w','scope','global');ok(mapping());traffic(43000);ok(delete())
            sh('ip','-6','addr','add','fd42:201::1/64','dev','upnp-w','nodad');time.sleep(.3)
            sh('ip','-6','addr','add','fd42:200::1/64','dev','upnp-w','nodad')
            uid=int(ok(pinhole())['values']['UniqueID']);traffic(42000,6,6);ok(pinop('DeletePinhole',uid));assert pid()==original
            return {'addresses':states,'v4_failure_v6_independent':True,'v6_failure_v4_independent':True,'pid_unchanged':True}
        case('WAN address categories change and dual-stack independence',networks)
        def flap():
            original=pid();ok(mapping(lease=120));uid=int(ok(pinhole(lease=120))['values']['UniqueID'])
            for duration in (1,6):
                sh('ip','link','set','upnp-w','down');time.sleep(duration)
                traffic(43000,expected=False);traffic(42000,6,6,False)
                sh('ip','link','set','upnp-w','up');sh('ip','-6','addr','add','fd42:200::1/64','dev','upnp-w','nodad');time.sleep(.4)
                deadline=time.monotonic()+5
                while True:
                    try:traffic(43000);traffic(42000,6,6);break
                    except AssertionError:
                        if time.monotonic()>deadline:raise
                        time.sleep(.2)
                assert pid()==original
            ok(delete());ok(pinop('DeletePinhole',uid))
        case('WAN short and longer link loss automatic recovery',flap)
        def event_repeat():
            original=pid()
            for i in range(5):
                sh('/etc/init.d/miniupnpd','reload');sh('env','ACTION=ifupdate','INTERFACE=upnpwan','sh','/etc/hotplug.d/iface/50-miniupnpd')
            time.sleep(.4);assert pid()==original
        case('Repeated reload and hotplug events preserve PID',event_repeat)
        def stress_case():
            original=pid();before=sh('cat',f'/proc/{original}/status')
            r=client(op='stress',count=200);assert 'dnat ip to' not in nft('upnp_prerouting');assert 'accept' not in nft('upnp_forward')
            after=sh('cat',f'/proc/{pid()}/status');assert pid()==original
            return {'cycles':r['cycles'],'rss_before':re.search(r'VmRSS:\s+(.*)',before).group(1),'rss_after':re.search(r'VmRSS:\s+(.*)',after).group(1),'fd_count':len(os.listdir(f'/proc/{original}/fd'))}
        case('Bounded mixed TCP/UDP stress and resource sample',stress_case)
        def idle():
            original=pid();before=sh('logread','-e','miniupnpd');time.sleep(10);after=sh('logread','-e','miniupnpd');assert not added_logs(before,after),added_logs(before,after);assert pid()==original
            return {'seconds':10,'new_logs':0}
        case('Short idle no repeated daemon logs',idle)
        with open(output+'.nft','w') as f:f.write(sh('nft','list','ruleset'))
        with open(output+'.log','w') as f:f.write(sh('logread','-e','miniupnpd'))
    finally:
        for server in servers:server.terminate()
        for server in servers:server.wait(timeout=3)
    return not any(r['status']=='FAIL' for r in results)


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--client':
        print(json.dumps(client_call(json.loads(sys.argv[2]))))
    elif len(sys.argv)>1 and sys.argv[1]=='--echo':
        echo(*map(int,sys.argv[2:]))
    else:
        sys.exit(0 if run_suite(sys.argv[1] if len(sys.argv)>1 else '/tmp/upnp-results.json') else 1)
