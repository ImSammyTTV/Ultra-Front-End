// Theme music: a game's theme plays quietly while its page is open, and fades out when you leave or start it.
// It finds the theme on YouTube and plays it through YouTube's own player with the picture hidden (nothing is
// downloaded). The song picked for each game is remembered, and "Next song" in Settings tries another if it's wrong.
// Your own song for a game: put it in this add-on's folder named after the game ("Hades II.mp3", or .m4a, .ogg...); it plays instead.
UFE.addon({
  id: 'themes',
  mount(api) {
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;left:-9999px;top:0;width:200px;height:120px;opacity:0;pointer-events:none';
    api.add('home', host);
    let player = null, audio = null, current = '', token = 0;
    const level = () => ({ low: 15, mid: 30, high: 50 })[api.settings().volume || 'mid'];
    const picks = () => api.store.get('picks', {});  // game id -> { id, title, n }: the song chosen, and which result it was

    // eases one sound's volume to a level over a second, then calls done. Each sound has its own fade, so a song fading
    // out always finishes (and stops) even while the next one fades in.
    const ramp = (p, a, from, to, done) => {
      clearInterval(p?._fade ?? a?._fade);
      let i = 0;
      const t = setInterval(() => {
        i++;
        const v = from + (to - from) * Math.min(1, i / 20);
        try { if (p) p.setVolume(v); if (a) a.volume = v / 100; } catch {}
        if (i >= 20) { clearInterval(t); done?.(); }
      }, 50);
      if (p) p._fade = t; if (a) a._fade = t;
    };
    const stop = () => {
      token++;
      const p = player, a = audio;
      player = null; audio = null; current = '';
      if (!p && !a) return;
      ramp(p, a, level(), 0, () => { try { p?.destroy(); } catch {} a?.pause(); if (a) a.src = ''; box?.remove(); });
    };
    // a theme from YouTube: the first result that's a song's length (1 to 10 minutes) and says theme, OST or music
    const find = async (g, skip = 0) => {
      const results = await api.youtube(`${g.title} main theme OST`);
      const good = results.filter(r => r.seconds >= 60 && r.seconds <= 600 && /theme|ost|soundtrack|music|title/i.test(r.title) && !/reaction|review|trailer|gameplay|walkthrough|cover|piano/i.test(r.title));
      const list = good.length ? good : results.filter(r => r.seconds >= 60 && r.seconds <= 900);
      return list.length ? list[skip % list.length] : null;
    };
    const playYouTube = async (g, mine) => {
      const saved = picks()[g.id];
      const pick = saved || await find(g);
      if (!pick || mine !== token) return;
      if (!saved) api.store.set('picks', { ...picks(), [g.id]: { id: pick.id, title: pick.title, n: 0 } });
      if (api.settings().save) {
        const c = await api.request('/api/themes/cached?id=' + pick.id).catch(() => ({}));
        if (mine !== token) return;
        if (c.saved) return playAudio(`/api/themes/file?id=${pick.id}`);
        api.request('/api/themes/save', { id: pick.id }).catch(() => {});  // ready for next time
      }
      await api.youtubePlayer();
      if (mine !== token) return;
      const slot = document.createElement('div');
      host.appendChild(slot);  // its own place: the last song's player is still fading out beside it
      player = new YT.Player(slot, {
        videoId: pick.id, width: 200, height: 120,
        // data saver: the smallest picture YouTube has, once (not looping), stopped after a minute
        playerVars: { autoplay: 1, controls: 0, disablekb: 1, playsinline: 1, rel: 0, ...(api.settings().saver ? {} : { loop: 1, playlist: pick.id }) },
        events: {
          onReady: e => { if (mine !== token) return e.target.destroy();
            if (api.settings().saver) { try { e.target.setPlaybackQuality('tiny'); } catch {} api.after(60000, () => { if (mine === token) stop(); }); }
            e.target.setVolume(0); e.target.playVideo(); ramp(e.target, null, 0, level()); },
          onError: () => { if (mine !== token) return; next(g, true); },  // not allowed to play outside YouTube: the next one
        },
      });
    };
    const playAudio = url => {
      audio = new Audio(url);
      audio.loop = true; audio.volume = 0;
      audio.play().then(() => ramp(null, audio, 0, level())).catch(() => {});
    };
    const play = async g => {
      if (!g || current === g.id) return;
      stop();
      const mine = ++token;
      current = g.id;
      // your own file first, if there is one
      const own = (await api.ownFiles?.()) || [];
      const file = own.find(f => /\.(mp3|m4a|ogg|wav|flac|opus)$/i.test(f) && [g.id, g.title.toLowerCase()].includes(f.replace(/\.[^.]+$/, '').toLowerCase()));  // named after the game or its id
      if (file) {
        audio = new Audio(api.fileUrl(file));  // (playAudio below does the same for a saved song)
        audio.loop = true; audio.volume = 0;
        audio.play().then(() => ramp(null, audio, 0, level())).catch(() => {});
        return;
      }
      playYouTube(g, mine);
    };
    // the song was wrong: the next result for this game, remembered from now on
    const next = async (g, quiet) => {
      const was = picks()[g.id], n = (was?.n || 0) + 1;
      const pick = await find(g, n);
      if (!pick) return;
      api.store.set('picks', { ...picks(), [g.id]: { id: pick.id, title: pick.title, n } });
      if (!quiet) api.toast(`Theme for ${g.title}: ${pick.title}`, 3500);
      if (current === g.id) { current = ''; play(g); }
    };
    this.next = next;
    this.last = null;
    api.on('game:details', ({ game }) => { this.last = game; if (api.settings().off) return; play(game); });
    api.on('game:details:close', stop);
    api.on('game:start', stop);
    api.every(1000, () => { if (current && !document.body.classList.contains('details-open')) stop(); });  // left the page some other way: silence
    this.stop = stop;
  },
  unmount() { this.stop?.(); },
  options(api) {
    const s = api.settings(), vols = [['low', 'Low'], ['mid', 'Medium'], ['high', 'High']];
    const at = Math.max(0, vols.findIndex(([k]) => k === (s.volume || 'mid')));
    const last = this.last, pick = last && (api.store.get('picks', {})[last.id]);
    return [
      { kind: 'row', label: 'Play themes', value: s.off ? 'Off' : 'On', sub: "On a game's page", act: () => { api.saveSettings({ off: !s.off }); renderPanel(); } },
      { kind: 'row', label: 'Save songs on this PC', value: s.save ? 'On' : 'Off', sub: 'Each theme is saved the first time it plays, then plays from your PC with no data',
        act: () => { api.saveSettings({ save: !s.save }); renderPanel(); } },
      { kind: 'row', label: 'Data saver', value: s.saver ? 'On' : 'Off', sub: 'Lowest quality, plays once, stops after a minute. Your own songs use no data',
        act: () => { api.saveSettings({ saver: !s.saver }); renderPanel(); } },
      { kind: 'row', label: 'Volume', value: vols[at][1], act: () => { api.saveSettings({ volume: vols[(at + 1) % vols.length][0] }); renderPanel(); } },
      ...(last ? [{ kind: 'row', label: `Next song for ${last.title}`, sub: pick ? `Now: ${pick.title}` : 'Tries another theme if this one is wrong',
        act: () => this.next?.(last).then(() => renderPanel()) }] : []),
    ];
  },
});
