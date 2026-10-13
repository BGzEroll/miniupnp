#!/usr/bin/env python3
"""Ensure this LuCI view and menu have complete Simplified Chinese entries."""
import ast
import json
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent
package = root / 'luci-app-upnp'
catalog = {}
key = value = None
field = None
for line in (package / 'po/zh_Hans/upnp.po').read_text().splitlines() + ['msgid ""']:
    if line.startswith('msgid '):
        if key is not None and value is not None:
            catalog[key] = value
        key, value, field = ast.literal_eval(line[6:]), None, 'id'
    elif line.startswith('msgstr '):
        value, field = ast.literal_eval(line[7:]), 'str'
    elif line.startswith('"'):
        if field == 'id':
            key += ast.literal_eval(line)
        elif field == 'str':
            value += ast.literal_eval(line)

view = (package / 'htdocs/luci-static/resources/view/upnp/upnp.js').read_text()
keys = {ast.literal_eval("'" + key + "'") for key in re.findall(r"_\('((?:\\.|[^'\\])*)'\)", view)}
menu = json.loads((package / 'root/usr/share/luci/menu.d/luci-app-upnp.json').read_text())
keys.update(entry['title'] for entry in menu.values() if 'title' in entry)
missing = sorted(key for key in keys if not catalog.get(key))
assert not missing, missing
print(json.dumps({'status': 'PASS', 'view_and_menu_strings': len(keys), 'missing': missing}))
