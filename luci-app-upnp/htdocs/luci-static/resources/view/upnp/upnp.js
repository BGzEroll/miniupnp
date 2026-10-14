'use strict';
'require view';
'require dom';
'require poll';
'require uci';
'require rpc';
'require form';
'require ui';

var callInitAction, callUpnpGetStatus, callUpnpDeleteRule, handleDelRule;

callInitAction = rpc.declare({
	object: 'luci',
	method: 'setInitAction',
	params: [ 'name', 'action' ],
	expect: { result: false }
});

callUpnpGetStatus = rpc.declare({
	object: 'luci.upnp',
	method: 'get_status',
	expect: {  }
});

callUpnpDeleteRule = rpc.declare({
	object: 'luci.upnp',
	method: 'delete_rule',
	params: [ 'token' ],
	expect: { result : "Failed" },
});

handleDelRule = function(num, ev) {
	var button = ev.currentTarget, row = dom.parent(button, '.tr');
	row.style.opacity = 0.5;
	button.classList.add('spinning');
	button.disabled = true;
	button.blur();
	return callUpnpDeleteRule(num).then(function(result) {
		if (result != 'OK' && result != 'Not found')
			ui.addNotification(null, E('p', _('Failed to delete the mapping. Please try again.')), 'error');
	}, function() {
		ui.addNotification(null, E('p', _('The deletion request did not complete. Refresh the list to confirm its status.')), 'error');
	}).then(function() {
		return callUpnpGetStatus();
	}).then(L.bind(function(status) {
		this.poll_status(document, [status]);
	}, this), function() {
		ui.addNotification(null, E('p', _('Failed to refresh the mapping list.')), 'error');
	}).finally(function() {
		row.style.opacity = '';
		button.classList.remove('spinning');
		button.disabled = false;
	});
};

return view.extend({
	load: function() {
		return Promise.all([
			callUpnpGetStatus(),
			uci.load('upnpd')
		]);
	},

	poll_status: function(nodes, data) {
		var view = this;

		var rules = Array.isArray(data[0].rules) ? data[0].rules : [];

		var rows = rules.map(function(rule) {
			return [
				(rule.family == 6 ? 'IPv6 ' : 'IPv4 ') + rule.proto,
				rule.family == 6 ? '—' : rule.extport,
				rule.intaddr,
				rule.host_hint || _('Unknown'),
				rule.intport,
				'%h'.format(rule.descr),
				E('button', {
					'class': 'btn cbi-button-remove',
					'click': L.bind(handleDelRule, view, rule.num)
				}, [ _('Delete') ])
			];
		});

		cbi_update_table(nodes.querySelector('#upnp_status_table'), rows, E('em', _('There are no active redirects.')));

		return;
	},

	render: function(data) {

		var m, s, o;

		m = new form.Map('upnpd', [_('Universal Plug & Play')],
			_('UPnP allows clients in the local network to automatically configure the router.'));

		s = m.section(form.GridSection, '_active_rules');

		s.render = L.bind(function(view, section_id) {
			var table = E('table', { 'class': 'table cbi-section-table', 'id': 'upnp_status_table' }, [
				E('tr', { 'class': 'tr table-titles' }, [
					E('th', { 'class': 'th' }, _('Protocol')),
					E('th', { 'class': 'th' }, _('External Port')),
					E('th', { 'class': 'th' }, _('Client Address')),
					E('th', { 'class': 'th' }, _('Host')),
					E('th', { 'class': 'th' }, _('Client Port')),
					E('th', { 'class': 'th' }, _('Description')),
					E('th', { 'class': 'th cbi-section-actions' }, '')
				])
			]);

			var rules = Array.isArray(data[0].rules) ? data[0].rules : [];

			var rows = rules.map(function(rule) {
				return [
					(rule.family == 6 ? 'IPv6 ' : 'IPv4 ') + rule.proto,
					rule.family == 6 ? '—' : rule.extport,
					rule.intaddr,
					rule.host_hint || _('Unknown'),
					rule.intport,
					'%h'.format(rule.descr),
					E('button', {
						'class': 'btn cbi-button-remove',
						'click': L.bind(handleDelRule, view, rule.num)
					}, [ _('Delete') ])
				];
			});

			cbi_update_table(table, rows, E('em', _('There are no active redirects.')));

			return E('div', { 'class': 'cbi-section cbi-tblsection' }, [
					E('h3', _('Active UPnP Redirects')), table ]);
		}, o, this);

		s = m.section(form.NamedSection, 'config', 'upnpd', _('MiniUPnP settings'));
		s.addremove = false;
		s.tab('general',  _('General Settings'));
		s.tab('advanced', _('Advanced Settings'));

		o = s.taboption('general', form.Flag, 'enabled', _('Start UPnP and NAT-PMP service'));
		o.rmempty  = false;

		s.taboption('general', form.Flag, 'enable_upnp', _('Enable UPnP functionality')).default = '1'
		s.taboption('general', form.Flag, 'enable_natpmp', _('Enable NAT-PMP and PCP functionality')).default = '1'

		o = s.taboption('general', form.Flag, 'ipv6_disable', _('Disable IPv6 pinholes'));
	o.default = '0';
	o.rmempty = false;
	s.taboption('advanced', form.Value, 'upnp_lease_file6', _('IPv6 lease file')).placeholder = '/var/run/miniupnpd.leases6';

	s.taboption('general', form.Flag, 'secure_mode', _('Enable secure mode'),
			_('Allow adding forwards only to requesting ip addresses')).default = '1'

		s.taboption('general', form.Flag, 'igdv1', _('Enable IGDv1 mode'),
			_('Advertise as IGDv1 device instead of IGDv2')).default = '0'

		s.taboption('general', form.Flag, 'log_output', _('Enable additional logging'),
			_('Log normal mapping requests'))

		s.taboption('general', form.Value, 'download', _('Downlink'),
			_('Value in KByte/s, informational only')).rmempty = true

		s.taboption('general', form.Value, 'upload', _('Uplink'),
			_('Value in KByte/s, informational only')).rmempty = true

		o = s.taboption('general', form.Value, 'port', _('Port'))
		o.datatype = 'port'
		o.default  = 5000

		s.taboption('advanced', form.Flag, 'system_uptime', _('Report system instead of daemon uptime')).default = '1'

		s.taboption('advanced', form.Value, 'uuid', _('Device UUID'))
		s.taboption('advanced', form.Value, 'serial_number', _('Announced serial number'))
		s.taboption('advanced', form.Value, 'model_number', _('Announced model number'))

		o = s.taboption('advanced', form.Value, 'notify_interval', _('Notify interval'))
		o.datatype    = 'uinteger'
		o.placeholder = 900

		o = s.taboption('advanced', form.Value, 'presentation_url', _('Presentation URL'))
		o.placeholder = 'http://192.168.1.1/'

		o = s.taboption('advanced', form.Value, 'upnp_lease_file', _('UPnP lease file'))
		o.placeholder = '/var/run/miniupnpd.leases'

		s = m.section(form.GridSection, 'perm_rule', _('MiniUPnP ACLs'),
			_('ACLs specify which external ports may be redirected to which internal addresses and ports'))

		s.sortable  = true
		s.anonymous = true
		s.addremove = true

		s.option(form.Value, 'comment', _('Comment'))

		o = s.option(form.Value, 'ext_ports', _('External ports'))
		o.datatype    = 'portrange'
		o.placeholder = '0-65535'

		o = s.option(form.Value, 'int_addr', _('Internal addresses'))
		o.datatype    = 'ip4addr'
		o.placeholder = '0.0.0.0/0'

		o = s.option(form.Value, 'int_ports', _('Internal ports'))
		o.datatype    = 'portrange'
		o.placeholder = '0-65535'

		o = s.option(form.ListValue, 'action', _('Action'))
		o.value('allow', _('Allow'));
		o.value('deny', _('Deny'));

		return m.render().then(L.bind(function(m, nodes) {
			poll.add(L.bind(function() {
				return Promise.all([
					callUpnpGetStatus()
				]).then(L.bind(this.poll_status, this, nodes));
			}, this), 5);
			return nodes;
		}, this, m));
	}
});
