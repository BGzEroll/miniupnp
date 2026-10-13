#!/usr/bin/env python3
"""Bounded dual-stack load and idle monitor; lab.sh must already be active."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
spec=importlib.util.spec_from_file_location('integration',os.path.join(os.path.dirname(__file__),'integration.py'))
t=importlib.util.module_from_spec(spec);spec.loader.exec_module(t)
seconds=int(sys.argv[2]) if len(sys.argv)>2 else 300
output=sys.argv[1] if len(sys.argv)>1 else '/tmp/upnp-soak.json'
samples=[];original=t.pid();failures=[];cycles=0

def snapshot(phase):
    p=t.pid();status=t.sh('cat',f'/proc/{p}/status');stat=t.sh('cat',f'/proc/{p}/stat').split()
    samples.append({'elapsed':round(time.monotonic()-started,2),'phase':phase,'pid':p,'rss_kb':int(re.search(r'VmRSS:\s+(\d+)',status).group(1)),
                    'fds':len(os.listdir(f'/proc/{p}/fd')),'cpu_ticks':int(stat[13])+int(stat[14]),
                    'nat_rules':t.nft('upnp_prerouting').count('dnat ip to'),'pinholes':t.nft('upnp_forward').count('pinhole-')})
    if p!=original:failures.append('unexpected restart')
    with open(output,'w') as f:json.dump({'seconds':seconds,'cycles':cycles,'failures':failures,'samples':samples},f,indent=2)

started=time.monotonic();snapshot('start')
# Two namespaces simultaneously request IPv4 TCP/UDP and IPv6 PCP mappings.
# Each worker is paced; load remains inside the VM and below 20 requests/sec.
worker='''import sys,time,json
sys.path.insert(0,__TEST_DIRECTORY__)
import integration as t
for n in range(80):
 for family in (4,6):
  r=t.pcp(family=family,proto=17 if n%2 else 6,iport=46000+n%20,eport=47000+n%20 if family==4 else 46000+n%20,client=X_CLIENT6 if family==6 else X_CLIENT4)
  assert r['error']==0,r
  r=t.pcp(family=family,proto=17 if n%2 else 6,iport=46000+n%20,eport=r['eport'],lifetime=0,client=X_CLIENT6 if family==6 else X_CLIENT4)
  assert r['error']==0,r
 time.sleep(.2)
'''
processes=[]
for ns,ip6,ip4 in [('lan','fd42:100::2','198.18.0.2'),('other','fd42:100::3','198.18.0.3')]:
    processes.append(subprocess.Popen(['ip','netns','exec','upnp-'+ns,'python3','-c',worker.replace('__TEST_DIRECTORY__',repr(os.path.dirname(t.SELF))).replace('X_CLIENT6',repr(ip6)).replace('X_CLIENT4',repr('::ffff:'+ip4))],stdout=subprocess.PIPE,stderr=subprocess.PIPE))
while any(p.poll() is None for p in processes):
    snapshot('concurrent_load');time.sleep(2)
for p in processes:
    stdout,stderr=p.communicate()
    if p.returncode:failures.append(stderr.decode())
cycles=320
snapshot('load_finished')
if samples[-1]['nat_rules'] or samples[-1]['pinholes']:failures.append('rules remained after workload')
# Monitor idle first with no WAN IPv4, then with dual stack restored.
t.sh('ip','-4','addr','flush','dev','upnp-w','scope','global');time.sleep(.5)
logs_before=t.sh('logread','-e','miniupnpd')
idle_started=time.monotonic();restored=False
while time.monotonic()-idle_started<seconds:
    if not restored and time.monotonic()-idle_started>seconds/2:
        if t.added_logs(logs_before,t.sh('logread','-e','miniupnpd')):failures.append('new log during no-IPv4 idle')
        t.sh('ip','addr','add','198.19.0.1/24','dev','upnp-w');time.sleep(.5)
        logs_before=t.sh('logread','-e','miniupnpd');restored=True
    snapshot('dual_stack_idle' if restored else 'ipv6_only_idle');time.sleep(5)
if t.added_logs(logs_before,t.sh('logread','-e','miniupnpd')):failures.append('new log during dual-stack idle')
if not restored:t.sh('ip','addr','add','198.19.0.1/24','dev','upnp-w')
snapshot('done')
assert not failures,failures
assert max(x['rss_kb'] for x in samples)-samples[0]['rss_kb']<256,samples
assert max(x['fds'] for x in samples)==samples[0]['fds'],samples
print(json.dumps({'status':'PASS','cycles':cycles,'idle_seconds':seconds,'rss_start':samples[0]['rss_kb'],'rss_end':samples[-1]['rss_kb'],'cpu_ticks_idle':samples[-1]['cpu_ticks']-next(x['cpu_ticks'] for x in samples if x['phase']=='ipv6_only_idle'),'fds':samples[-1]['fds']}))
