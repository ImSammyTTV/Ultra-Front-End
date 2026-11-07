// Weather: the temperature next to the clock (and the humidity, if you want it), from Open-Meteo: free, no account.
// The place is the city of your time zone ("Australia/Sydney" -> Sydney) unless you choose another.
UFE.addon({
  id: 'weather',
  timer: 0,
  async mount(api) {
    const slot = api.slot('header');
    if (!slot) return;
    const el = document.createElement('span');
    el.id = 'addon-weather';
    el.className = 'addon-weather';
    const clock = slot.querySelector('#clock');
    clock ? clock.before(el) : slot.prepend(el);  // right next to the time
    const draw = async () => {
      const s = api.settings('weather'), unit = s.unit === 'f' ? 'fahrenheit' : 'celsius';
      try {
        const place = await this.place(s.city || (api.timezone() || '').split('/').pop().replace(/_/g, ' '));
        if (!place) { el.textContent = ''; return; }
        const q = `latitude=${place.latitude}&longitude=${place.longitude}&current=temperature_2m,relative_humidity_2m,weather_code&temperature_unit=${unit}`;
        const w = (await (await fetch(`https://api.open-meteo.com/v1/forecast?${q}`)).json()).current;
        el.innerHTML = `<b>${this.sky(w.weather_code)}</b>${Math.round(w.temperature_2m)}°${s.unit === 'f' ? 'F' : 'C'}${s.humidity ? `<small>${w.relative_humidity_2m}%</small>` : ''}`;
        el.title = `${place.name}`;
      } catch { /* offline: keep the last reading */ }
    };
    draw();
    this.timer = setInterval(draw, 15 * 60 * 1000);  // every 15 minutes
  },
  unmount() { clearInterval(this.timer); document.getElementById('addon-weather')?.remove(); },
  places: {},
  async place(name) {  // a city name to its coordinates, through Open-Meteo's own place search
    if (!name) return null;
    if (this.places[name]) return this.places[name];
    const r = await (await fetch(`https://geocoding-api.open-meteo.com/v1/search?count=1&name=${encodeURIComponent(name)}`)).json();
    return (this.places[name] = r.results?.[0] || null);
  },
  sky(code) {  // WMO weather code to a simple symbol
    return code === 0 ? '☀' : code <= 2 ? '⛅' : code <= 3 ? '☁' : code <= 48 ? '🌫' : code <= 67 || (code >= 80 && code <= 82) ? '🌧' : code <= 77 || code === 85 || code === 86 ? '❄' : '⛈';
  },
  options(api) {
    const s = api.settings('weather');
    return [
      { kind: 'row', label: 'Temperature in', value: s.unit === 'f' ? '°F' : '°C', act: () => api.saveSettings('weather', { unit: s.unit === 'f' ? 'c' : 'f' }) },
      { kind: 'row', label: 'Show humidity', value: s.humidity ? 'On' : 'Off', act: () => api.saveSettings('weather', { humidity: !s.humidity }) },
      { kind: 'row', label: 'Place', value: s.city || 'From your time zone', sub: 'Choose a city, or leave it to follow your time zone',
        act: () => api.ask('City for the weather (leave empty for your time zone)', city => api.saveSettings('weather', { city })) },
    ];
  },
});
