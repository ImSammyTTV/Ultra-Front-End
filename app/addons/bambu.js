// Bambu Lab: how your print is going, by the clock and in a card over your game, and a message when it's done.
// An example of api.hud: the card shows only while a game is running.
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
      draw(); card();
      was = p.state;
    };
    check();
    api.every(10000, check);
    // over the game: a card in the corner at the print's milestones
    // the picture of what's printing, from the print file on the printer (once per print; none for a print not kept there)
    let pic = { key: '', url: '' };
    const picture = async () => {
      const key = p.name || '';
      if (key === pic.key) return pic.url;
      pic = { key, url: '' };
      try { if ((await fetch('/api/bambu/preview', { cache: 'no-store' })).ok) pic.url = `/api/bambu/preview?k=${encodeURIComponent(key)}`; } catch {}
      return pic.url;
    };
    // the file name as a title: no underscores or .3mf, only Latin letters and numbers ("X2D_&_P2S_全覆盖外排气接口" -> "X2D & P2S")
    const nice = n => (n || '').replace(/\.(gcode\.)?3mf$|\.gcode$/i, '').replace(/[_]+/g, ' ').replace(/[^\p{Script=Latin}\d\s&+\-().,']/gu, ' ')
      .replace(/\s+/g, ' ').replace(/^[\s&+\-.,]+|[\s&+\-.,]+$/g, '').trim() || '3D print';
    // Only while it prints, and only at the moments that matter: as it starts (0%), at 25%, 50% and 75%, and when it
    // finishes, stops or pauses. Each time the card shows for 10 seconds, then goes again.
    let seen = { key: '', step: -1, state: '' }, showUntil = 0;
    const card = async () => {
      if (!p?.connected) return api.hud(null);
      const key = `${p.name}|${p.layers}`;
      if (key !== seen.key) seen = { key, step: -1, state: '' };  // a new print
      let show = false;
      if (active(p.state) && p.state !== 'PAUSE') {
        const step = Math.min(3, Math.floor((p.percent || 0) / 25));
        if (step > seen.step) { seen.step = step; show = true; }
      }
      if (p.state !== seen.state) {
        if (seen.state && ['FINISH', 'FAILED', 'PAUSE'].includes(p.state)) show = true;
        seen.state = p.state;
      }
      if (show) showUntil = Date.now() + 10000;
      if (Date.now() > showUntil) return api.hud(null);
      const name = nice(p.name), image = await picture(), place = api.settings().place || 'top-left';
      if (p.state === 'FINISH' || p.state === 'FAILED') return api.hud({ place, icon: 'printer', image, text: name, sub: p.state === 'FINISH' ? 'Print finished' : 'Print stopped', progress: p.state === 'FINISH' ? 100 : null });
      api.hud({ place, icon: 'printer', image, text: name, progress: p.percent,
        sub: [p.state === 'PAUSE' ? 'Paused' : p.state === 'PREPARE' ? 'Getting ready' : `${p.percent ?? 0}%`, p.remaining ? `${left(p.remaining)} left` : ''].filter(Boolean).join(' · ') });
    };
    api.every(2000, card);
  },
  options(api) {
    const set = patch => api.request('/api/bambu', patch).then(() => { api.toast('Saved'); renderPanel(); }).catch(e => api.toast(e.message));
    const PLACES = [['top-left', 'Top left'], ['top', 'Top middle'], ['top-right', 'Top right'], ['bottom-left', 'Bottom left'], ['bottom', 'Bottom middle'], ['bottom-right', 'Bottom right']];
    const at = Math.max(0, PLACES.findIndex(([k]) => k === (api.settings().place || 'top-left')));
    return [
      { kind: 'row', label: 'Card over the game', value: PLACES[at][1], sub: 'Where it sits on the screen while you play',
        act: () => { api.saveSettings({ place: PLACES[(at + 1) % PLACES.length][0] }); renderPanel(); } },
      { kind: 'row', label: 'Printer IP address', value: api.store.get('ip', '') || 'Not set', sub: "On the printer: Settings › Network (it's best to give it a fixed address in your router)",
        act: () => api.ask('Printer IP address', ip => { api.store.set('ip', ip); set({ ip }); }, 40) },
      { kind: 'row', label: 'Serial number', value: api.store.get('serial', '') || 'Not set', sub: 'On the printer: Settings › Device, or on the label on the back',
        act: () => api.ask('Printer serial number', serial => { api.store.set('serial', serial.toUpperCase()); set({ serial: serial.toUpperCase() }); }, 30) },
      { kind: 'row', label: 'Access code', value: api.store.get('hasCode', false) ? 'Saved' : 'Not set', sub: 'On the printer: Settings › Network (WLAN), the 8-character code. Kept on this PC only',
        act: () => api.ask('Printer access code', code => { api.store.set('hasCode', !!code); set({ code }); }, 20) },
    ];
  },
});
