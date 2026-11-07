// Bambu Lab: how your print is going, by the clock and in Quick Access, and a message when it's done.
// The app talks to the printer on your home network (LAN): its IP address, serial number and access code are on the
// printer's screen (Settings › Network, or WLAN / LAN Only). Nothing goes through Bambu's cloud.
UFE.addon({
  id: 'bambu',
  mount(api) {
    const el = document.createElement('span');
    el.className = 'bambu-chip';
    api.add('header', el);
    api.css(`.bambu-chip { display: inline-flex; align-items: center; gap: .7vh; margin-right: 2.2vh; font-variant-numeric: tabular-nums; }
      .bambu-chip:empty { display: none; }
      .bambu-chip i { display: inline-block; width: 6vh; height: .6vh; border-radius: .3vh; background: rgba(255,255,255,.22); overflow: hidden; }
      .bambu-chip i b { display: block; height: 100%; background: #fff; border-radius: inherit; transition: width .6s ease; }`);
    let p = null, was = '';
    const left = m => m == null ? '' : m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min`;
    const active = s => ['RUNNING', 'PREPARE', 'PAUSE', 'SLICING'].includes(s);
    const draw = () => {
      el.innerHTML = p && active(p.state) && p.percent != null
        ? `${api.icon('printer')}<span>${p.state === 'PAUSE' ? 'Paused' : `${p.percent}%`}</span><i><b style="width:${p.percent}%"></b></i>${p.remaining ? `<span>${left(p.remaining)}</span>` : ''}`
        : '';
      api.refresh();
    };
    const check = async () => {
      try { p = await api.request('/api/bambu'); } catch { return; }
      // a message when a print ends, whichever way
      if (active(was) && p.state === 'FINISH') { api.toast(`Print finished${p.name ? `: ${p.name}` : ''}`, 6000); api.sound(880, .08); }
      if (active(was) && p.state === 'FAILED') api.toast(`Print stopped${p.name ? `: ${p.name}` : ''}`, 6000);
      was = p.state;
      draw();
    };
    check();
    api.every(10000, check);
    api.quickAccess(() => {
      if (!p) return [];
      if (!p.setup) return [{ icon: 'printer', label: '3D printer', sub: 'Set it up in Settings › Add-ons', run: () => api.openSettings() }];
      if (!p.connected) return [{ icon: 'printer', label: '3D printer', sub: p.error ? `Can't reach it: ${p.error}` : 'Connecting…' }];
      const name = p.name || 'Print';
      const states = { RUNNING: 'Printing', PREPARE: 'Getting ready', PAUSE: 'Paused', FINISH: 'Finished', FAILED: 'Stopped', IDLE: 'Ready', SLICING: 'Slicing' };
      return [
        { icon: 'printer', label: active(p.state) || p.state === 'FINISH' ? name : '3D printer', value: active(p.state) && p.percent != null ? `${p.percent}%` : '',
          sub: [states[p.state] || 'Ready', active(p.state) && p.remaining ? `${left(p.remaining)} left` : '', p.layers ? `layer ${p.layer} of ${p.layers}` : ''].filter(Boolean).join(' · ') },
        ...(p.nozzle != null ? [{ icon: 'flame', label: 'Temperatures', sub: `Nozzle ${Math.round(p.nozzle)}°${p.nozzleTarget ? ` of ${Math.round(p.nozzleTarget)}°` : ''} · Bed ${Math.round(p.bed)}°${p.bedTarget ? ` of ${Math.round(p.bedTarget)}°` : ''}` }] : []),
      ];
    }, { title: '3D printer', icon: 'printer' });
  },
  options(api) {
    const set = patch => api.request('/api/bambu', patch).then(() => { api.toast('Saved'); renderPanel(); }).catch(e => api.toast(e.message));
    return [
      { kind: 'row', label: 'Printer IP address', value: api.store.get('ip', '') || 'Not set', sub: "On the printer: Settings › Network (it's best to give it a fixed address in your router)",
        act: () => api.ask('Printer IP address', ip => { api.store.set('ip', ip); set({ ip }); }, 40) },
      { kind: 'row', label: 'Serial number', value: api.store.get('serial', '') || 'Not set', sub: 'On the printer: Settings › Device, or on the label on the back',
        act: () => api.ask('Printer serial number', serial => { api.store.set('serial', serial.toUpperCase()); set({ serial: serial.toUpperCase() }); }, 30) },
      { kind: 'row', label: 'Access code', value: api.store.get('hasCode', false) ? 'Saved' : 'Not set', sub: 'On the printer: Settings › Network (WLAN), the 8-character code. Kept on this PC only',
        act: () => api.ask('Printer access code', code => { api.store.set('hasCode', !!code); set({ code }); }, 20) },
    ];
  },
});
