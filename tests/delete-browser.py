#!/usr/bin/env python3
"""Actual LuCI clicks with controlled RPC failure/absence; requires lab.sh."""
import json,os,pathlib,subprocess,time
from playwright.sync_api import sync_playwright

VM='root@192.168.114.210';ROOT=pathlib.Path(__file__).resolve().parent.parent
OUT=ROOT/'reports';OUT.mkdir(exist_ok=True);results=[]
def remote(cmd):return subprocess.check_output(['ssh',VM,cmd],text=True).strip()
def create(port):
    remote("python3 - <<'PY'\nimport sys\nsys.path.insert(0,'/tmp')\nimport integration as t\nt.ok(t.mapping(eport="+str(port)+",iport="+str(port+100)+",lease=600))\nPY")
def count(port):return sum(row['family']==4 and row['extport']==port for row in json.loads(remote('ubus call luci.upnp get_status'))['rules'])
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
    for action in ('normal','backend','malformed','transport','lost_reply','absent','refresh'):
        port=53400+len(results);create(port)
        context=browser.new_context(locale='zh-CN');page=context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(error.stack))
        page.goto('http://192.168.114.210/cgi-bin/luci/admin/services/upnp',wait_until='networkidle')
        if page.locator('input[name="luci_username"]').count():
            page.locator('input[name="luci_username"]').fill('root')
            page.locator('input[name="luci_password"]').fill('')
            with page.expect_navigation(wait_until='networkidle'):page.locator('input[name="luci_password"]').press('Enter')
        table=page.locator('#upnp_status_table');table.wait_for()
        row=table.locator('tr').filter(has=page.locator('td',has_text=str(port))).first
        # The theme may render div rows; locate using LuCI's .tr class.
        row=table.locator('.tr').filter(has=page.locator('.td',has_text=str(port))).first
        button=row.locator('button.cbi-button-remove');assert button.count()==1,(action,table.inner_text())
        state={'deleted':False,'refresh_failed':False}
        def intercept(route):
            request=route.request
            try:payload=json.loads(request.post_data or 'null')
            except ValueError:route.continue_();return
            messages=payload if isinstance(payload,list) else [payload]
            with (OUT/'delete-browser-rpc.log').open('a') as log:
                log.write(json.dumps({'action':action,'url':request.url,'methods':[m.get('params',[None,None,None])[1:3] for m in messages if isinstance(m,dict)]})+'\n')
            deletion=next((m for m in messages if isinstance(m,dict) and m.get('params',[None,None,None])[1:3]==['luci.upnp','delete_rule']),None)
            refresh=next((m for m in messages if isinstance(m,dict) and m.get('params',[None,None,None])[1:3]==['luci.upnp','get_status']),None)
            if deletion:
                state['deleted']=True
                if action in ('backend','malformed','refresh'):
                    data={'result':'Failed'} if action!='malformed' else {}
                    others=[m for m in messages if m['id']!=deletion['id']]
                    responses=[]
                    if others:
                        live=route.fetch(post_data=json.dumps(others if isinstance(payload,list) else others[0]))
                        responses=live.json();responses=responses if isinstance(responses,list) else [responses]
                    responses.append({'jsonrpc':'2.0','id':deletion['id'],'result':[0,data]})
                    route.fulfill(json=responses if isinstance(payload,list) else responses[0]);return
                if action=='transport':route.abort();return
                if action=='lost_reply':route.fetch();route.abort();return
                if action=='absent':remote('miniupnpdctl delete4 TCP '+str(port))
            if action=='refresh' and state['deleted'] and refresh:
                state['refresh_failed']=True;route.abort();return
            route.continue_()
        page.route('**/ubus**',intercept)
        button.click()
        if action in ('backend','malformed','refresh'):
            try:page.get_by_text('删除映射失败，请重试。',exact=True).wait_for(timeout=10000)
            except Exception:
                (OUT/'delete-browser-failure.txt').write_text(page.locator('body').inner_text());raise
        if action in ('transport','lost_reply'):
            page.get_by_text('删除请求未完成，请刷新列表确认实际状态。',exact=True).wait_for()
        if action=='refresh':page.get_by_text('刷新映射列表失败。',exact=True).wait_for()
        if action in ('normal','absent','lost_reply'):
            page.wait_for_function('(port) => !Array.from(document.querySelectorAll("#upnp_status_table .tr")).some(r => r.innerText.includes(String(port)))',arg=port)
            assert count(port)==0
        else:
            page.wait_for_function('(port) => Array.from(document.querySelectorAll("#upnp_status_table .tr")).some(r => r.innerText.includes(String(port)) && !r.querySelector("button").disabled && r.style.opacity === "")',arg=port)
            assert count(port)==1
        assert not errors,errors
        if action in ('normal','absent'):assert page.locator('.alert-message.error').count()==0
        results.append({'name':action,'status':'PASS','server_rules':count(port),'js_errors':errors})
        (OUT/'delete-browser.json').write_text(json.dumps(results,indent=2)+'\n');print('PASS',action,flush=True)
        page.unroute('**/ubus**',intercept);remote('miniupnpdctl delete4 TCP '+str(port));context.close()
    browser.close()
