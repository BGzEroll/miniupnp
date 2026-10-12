#!/usr/bin/env python3
"""Host Playwright smoke test; lab.sh and two fixture rules must be active.

Requires Playwright/Chromium on the host. Changes only the authorized VM UI.
"""
import json
import os
import pathlib
import subprocess
import time
from playwright.sync_api import sync_playwright

VM = 'root@192.168.114.210'
REPORTS = pathlib.Path(__file__).resolve().parent.parent / 'reports'
LOCALE = os.environ.get('BROWSER_LOCALE', 'en-US')
SUFFIX = '-zh' if LOCALE.lower().startswith('zh') else ''


def remote(command):
    return subprocess.check_output(['ssh', VM, command], text=True).strip()


def wait_remote(command, expected, timeout=12):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if remote(command) == expected:
            return
        time.sleep(.3)
    raise AssertionError((command, expected, remote(command)))


def open_ui(page):
    page.goto('http://192.168.114.210/cgi-bin/luci/admin/services/upnp', wait_until='networkidle')
    if page.locator('input[name="luci_username"]').count():
        page.locator('input[name="luci_username"]').fill('root')
        page.locator('input[name="luci_password"]').fill('')
        with page.expect_navigation(wait_until='networkidle'):
            page.locator('input[name="luci_password"]').press('Enter')
    page.locator('#upnp_status_table').wait_for()


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1000}, locale=LOCALE)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    open_ui(page)
    table = page.locator('#upnp_status_table')
    table.wait_for()
    table.get_by_text('IPv4 TCP', exact=True).wait_for()
    table.get_by_text('IPv6 TCP', exact=True).wait_for()
    assert '51910' in table.inner_text() and 'fd42:100::2' in table.inner_text()
    displayed = table.inner_text()
    pid = remote('pidof miniupnpd')
    if SUFFIX:
        for label in ('通用即插即用（UPnP）', '外部端口', '客户端地址', '客户端端口',
                      'MiniUPnP 设置', '启用 NAT-PMP 和 PCP 功能', '禁用 IPv6 防火墙端口放行',
                      'UPnP IGD 与 PCP'):
            assert page.get_by_text(label, exact=True).count(), label
        assert 'External Port' not in table.inner_text()
        page.get_by_text('高级设置', exact=True).click()
        assert page.get_by_text('IPv6 租约文件', exact=True).count()
        page.wait_for_timeout(400)
        page.screenshot(path=str(REPORTS / 'luci-zh-advanced.png'), full_page=True)
        page.get_by_text('常规设置', exact=True).click()
        page.wait_for_timeout(400)
    page.screenshot(path=str(REPORTS / ('luci' + SUFFIX + '.png')), full_page=True)
    for _ in range(2):
        table.locator('button.cbi-button-remove').first.click()
        page.wait_for_timeout(5500)
    assert table.locator('button.cbi-button-remove').count() == 0
    assert remote('pidof miniupnpd') == pid
    assert json.loads(remote('ubus call luci.upnp get_status'))['rules'] == []
    # Exercise LuCI Save & Apply against the real procd service.
    enabled = page.locator('input[data-widget-id="widget.cbid.upnpd.config.enabled"]')
    assert enabled.count() == 1
    enabled.uncheck(force=True)
    page.locator('.cbi-page-actions .cbi-button-apply li[data-value="0"]').click()
    wait_remote('/etc/init.d/miniupnpd running >/dev/null 2>&1; echo $?', '1')
    # LuCI confirms rollback-protected apply asynchronously; wait for the
    # overlay to finish before interacting with the next checkbox.
    page.wait_for_function("!document.body.classList.contains('modal-overlay-active')", timeout=45000)
    open_ui(page)
    enabled.check(force=True)
    page.locator('.cbi-page-actions .cbi-button-apply li[data-value="0"]').click()
    wait_remote('/etc/init.d/miniupnpd running >/dev/null 2>&1; echo $?', '0')
    page.wait_for_function("!document.body.classList.contains('modal-overlay-active')", timeout=45000)
    assert remote('uci get upnpd.config.enabled') == '1'
    assert not errors, errors
    result = {'status': 'PASS', 'locale': LOCALE, 'url': page.url, 'js_errors': errors,
              'displayed_rules': displayed, 'delete_preserved_pid': pid,
              'enabled_save_apply': True}
    (REPORTS / ('luci-browser' + SUFFIX + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    browser.close()
