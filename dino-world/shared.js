(function (global) {
  "use strict";

  const INK = "#24312c";

  const DINOS = [
    { id: "rex", name: "Rex", kind: "rex", body: "#6BBF59", belly: "#E7F6D4", spot: "#4E9E45" },
    { id: "trixie", name: "Trixie", kind: "trixie", body: "#F4A261", belly: "#FFE3C4", spot: "#E08A3C" },
    { id: "steg", name: "Steg", kind: "steg", body: "#2A9D8F", belly: "#D5F3EE", spot: "#1F7F73" },
    { id: "lofty", name: "Lofty", kind: "lofty", body: "#4C9BE8", belly: "#D9ECFF", spot: "#2E74C4" },
    { id: "pip", name: "Pip", kind: "pip", body: "#9B7EDE", belly: "#EDE4FF", spot: "#7354C4" },
    { id: "nib", name: "Nib", kind: "nib", body: "#E9C46A", belly: "#FFF3CF", spot: "#D0A43E" },
    { id: "zip", name: "Zip", kind: "zip", body: "#E76F51", belly: "#FFD9CF", spot: "#C8523A" },
    { id: "sail", name: "Sail", kind: "sail", body: "#3D7A8C", belly: "#D5EEF3", spot: "#2A5C6B" }
  ];

  function svg(inner, viewBox) {
    return `<svg viewBox="${viewBox || "0 0 100 100"}" aria-hidden="true">${inner}</svg>`;
  }

  function eye(x, y, r) {
    const size = r || 8;
    return `<circle cx="${x}" cy="${y}" r="${size}" fill="${INK}" stroke="none"/>` +
      `<circle cx="${x + size * 0.32}" cy="${y - size * 0.32}" r="${size * 0.34}" fill="#fff" stroke="none"/>`;
  }

  function cheek(x, y) {
    return `<circle cx="${x}" cy="${y}" r="6.5" fill="#f4a9a2" stroke="none"/>`;
  }

  function smile(x1, y, x2, dip) {
    const mid = (x1 + x2) / 2;
    return `<path d="M${x1} ${y} Q${mid} ${y + (dip || 10)} ${x2} ${y}" fill="none" stroke="${INK}" stroke-width="4" stroke-linecap="round"/>`;
  }

  function blob(d, fill, sw) {
    return `<path d="${d}" fill="${fill}" stroke="${INK}" stroke-width="${sw || 4}" stroke-linejoin="round" stroke-linecap="round"/>`;
  }

  function ell(cx, cy, rx, ry, fill, stroke) {
    const line = stroke === false ? `stroke="none"` : `stroke="${INK}" stroke-width="4"`;
    return `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="${fill}" ${line}/>`;
  }

  function drawDino(dino, override) {
    const body = (override && override.body) || dino.body;
    const belly = (override && override.belly) || dino.belly;
    const spot = (override && override.spot) || dino.spot;
    const b = body;
    const g = belly;
    const s = spot;
    let inner = "";
    if (dino.kind === "rex") {
      inner = [
        blob("M86 146 C46 140 28 118 38 104 C54 122 74 130 92 132 Z", b),
        ell(118, 142, 54, 40, b),
        ell(126, 154, 32, 22, g, false),
        blob("M96 168 C92 196 114 198 116 170 Z", b),
        blob("M136 168 C134 198 158 196 152 164 Z", b),
        blob("M158 126 C178 118 184 140 164 146 Z", b),
        ell(178, 96, 40, 34, b),
        ell(210, 108, 22, 14, b),
        ell(168, 112, 10, 8, s, false),
        eye(186, 88, 8),
        cheek(166, 108),
        smile(194, 112, 218, 9)
      ].join("");
    } else if (dino.kind === "trixie") {
      inner = [
        ell(150, 78, 48, 40, s),
        blob("M118 70 L132 42 L146 70 Z", g),
        blob("M168 86 L196 70 L176 100 Z", g),
        blob("M146 92 L168 64 L162 102 Z", g),
        ell(132, 138, 62, 42, b),
        ell(138, 150, 36, 22, g, false),
        blob("M96 162 C92 192 116 194 118 164 Z", b),
        blob("M150 164 C150 194 176 192 170 160 Z", b),
        ell(186, 112, 36, 28, b),
        ell(214, 120, 16, 12, b),
        eye(192, 104, 7),
        cheek(174, 120),
        smile(200, 124, 220, 7)
      ].join("");
    } else if (dino.kind === "steg") {
      inner = [
        blob("M70 150 C36 146 24 132 34 120 C48 134 64 138 78 140 Z", b),
        blob("M48 158 L62 174 L70 156 Z", s),
        blob("M36 150 L48 166 L58 148 Z", s),
        ell(124, 146, 58, 36, b),
        ell(128, 156, 34, 18, g, false),
        blob("M78 118 Q92 62 110 116 Z", s),
        blob("M108 112 Q124 48 142 112 Z", s),
        blob("M140 116 Q156 58 172 120 Z", s),
        blob("M168 122 Q180 78 194 128 Z", s),
        blob("M100 168 C98 194 120 196 122 168 Z", b),
        blob("M146 168 C148 196 172 194 166 164 Z", b),
        ell(196, 124, 26, 20, b),
        eye(202, 118, 6),
        smile(206, 130, 220, 6)
      ].join("");
    } else if (dino.kind === "lofty") {
      inner = [
        blob("M92 154 C48 150 30 134 40 118 C58 132 78 138 96 140 Z", b),
        ell(118, 156, 52, 34, b),
        ell(124, 166, 30, 16, g, false),
        blob("M92 150 C108 78 126 46 150 28 C132 58 124 96 128 150 Z", b),
        ell(156, 30, 20, 16, b),
        eye(162, 26, 5),
        smile(160, 36, 174, 5),
        blob("M96 170 C94 196 116 198 118 170 Z", b),
        blob("M132 172 C134 198 156 196 150 168 Z", b),
        ell(108, 150, 8, 6, s, false),
        ell(126, 142, 7, 5, s, false)
      ].join("");
    } else if (dino.kind === "pip") {
      inner = [
        ell(78, 116, 54, 22, s),
        ell(176, 112, 58, 24, s),
        ell(124, 124, 36, 28, b),
        ell(128, 132, 18, 12, g, false),
        blob("M108 146 C106 168 124 170 126 146 Z", b),
        blob("M136 146 C138 168 156 166 148 144 Z", b),
        ell(164, 96, 28, 22, b),
        blob("M176 78 L188 96 L168 98 Z", s),
        ell(188, 100, 16, 8, b),
        eye(168, 90, 6),
        smile(176, 104, 194, 5)
      ].join("");
    } else if (dino.kind === "nib") {
      inner = [
        blob("M46 132 C28 124 24 112 36 108 C44 118 58 122 64 120 Z", b),
        ell(40, 118, 12, 12, s),
        ell(128, 142, 70, 38, b),
        ell(132, 154, 42, 18, g, false),
        ell(92, 112, 14, 12, s),
        ell(124, 104, 16, 13, s),
        ell(156, 108, 14, 12, s),
        ell(184, 118, 12, 10, s),
        blob("M86 164 C84 190 108 192 110 164 Z", b),
        blob("M150 164 C152 192 176 190 170 160 Z", b),
        ell(198, 124, 24, 20, b),
        eye(204, 118, 6),
        smile(200, 132, 216, 6)
      ].join("");
    } else if (dino.kind === "zip") {
      inner = [
        blob("M70 120 C34 112 24 96 36 88 C50 102 66 108 78 106 Z", b),
        ell(112, 132, 40, 30, b),
        ell(118, 142, 20, 14, g, false),
        blob("M96 154 C100 186 118 196 124 164 Z", b),
        blob("M128 150 C156 168 168 196 150 168 Z", b),
        blob("M142 176 L156 188 L148 168 Z", s),
        ell(156, 100, 30, 26, b),
        blob("M150 78 Q164 64 170 86 Q158 80 150 90 Z", s),
        ell(182, 104, 14, 10, b),
        eye(160, 94, 7),
        cheek(146, 108),
        smile(168, 110, 188, 6)
      ].join("");
    } else {
      inner = [
        blob("M78 146 C40 142 26 126 36 114 C52 128 68 134 84 136 Z", b),
        ell(124, 148, 56, 36, b),
        ell(130, 158, 32, 18, g, false),
        blob("M96 104 L112 52 L128 112 Z", s),
        blob("M126 100 L144 40 L160 114 Z", s),
        blob("M156 108 L170 58 L186 120 Z", s),
        blob("M100 168 C98 194 120 196 122 168 Z", b),
        blob("M148 168 C150 196 174 194 168 164 Z", b),
        ell(196, 128, 34, 16, b),
        ell(214, 122, 16, 12, b),
        eye(188, 118, 6),
        smile(196, 132, 220, 6)
      ].join("");
    }
    return svg(inner, "0 0 240 200");
  }

  function worldSvg() {
    return `<svg class="world" viewBox="0 0 1200 800" preserveAspectRatio="xMidYMax slice" aria-hidden="true">
      <rect width="1200" height="800" fill="#8ecae6"/>
      <circle cx="1030" cy="360" r="72" fill="none" stroke="#ffe3a3" stroke-width="12"/>
      <circle cx="1030" cy="360" r="48" fill="#ffd166"/>
      <g class="cloud-a" fill="#fff">
        <ellipse cx="250" cy="148" rx="78" ry="30"/>
        <ellipse cx="304" cy="136" rx="48" ry="38"/>
        <ellipse cx="196" cy="142" rx="42" ry="28"/>
      </g>
      <g class="cloud-b" fill="#fff">
        <ellipse cx="820" cy="196" rx="86" ry="32"/>
        <ellipse cx="886" cy="184" rx="52" ry="40"/>
        <ellipse cx="760" cy="190" rx="46" ry="28"/>
      </g>
      <ellipse cx="260" cy="840" rx="540" ry="240" fill="#8ed18a"/>
      <ellipse cx="980" cy="870" rx="580" ry="270" fill="#6dbf78"/>
    </svg>`;
  }

  function homeIcon() {
    return `<svg viewBox="0 0 48 48"><path d="M8 22 24 9 40 22 V40 H31 V28 H17 V40 H8 Z" fill="#fff8ee" stroke="#24312c" stroke-width="3" stroke-linejoin="round"/></svg>`;
  }

  function starHtml(count) {
    return `<svg viewBox="0 0 24 24"><path d="M12 2.6 14.8 8.6 21.2 9.4 16.5 13.9 17.8 20.4 12 17.2 6.2 20.4 7.5 13.9 2.8 9.4 9.2 8.6 Z"/></svg><span>${count}</span>`;
  }

  function paw(cls) {
    return `<svg viewBox="0 0 48 48" class="paw ${cls}"><ellipse cx="24" cy="30" rx="11" ry="9"/><circle cx="12" cy="16" r="4.5"/><circle cx="24" cy="12" r="5"/><circle cx="36" cy="16" r="4.5"/></svg>`;
  }

  function trailHtml(filled, showNext) {
    let html = "";
    for (let i = 0; i < 5; i++) {
      const cls = i < filled ? "on" : (showNext && i === filled ? "now" : "");
      html += paw(cls);
    }
    return html;
  }

  function shuffle(list) {
    const a = list.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      const t = a[i];
      a[i] = a[j];
      a[j] = t;
    }
    return a;
  }

  function load(key, fallback) {
    try {
      const saved = JSON.parse(localStorage.getItem(key) || "null");
      if (saved && typeof saved === "object") return Object.assign(fallback(), saved);
    } catch (err) { /* private mode */ }
    return fallback();
  }

  function save(key, state) {
    try { localStorage.setItem(key, JSON.stringify(state)); } catch (err) { /* ignore */ }
  }

  function createAudio() {
    let ctx = null;
    let speaking = false;
    let queue = [];
    let soundOn = true;

    function setup() {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return;
      if (!ctx) ctx = new AC();
      if (ctx.state === "suspended") ctx.resume();
    }

    function tone(freq, when, dur, type, vol) {
      if (!ctx) return;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, when);
      gain.gain.setValueAtTime(0.0001, when);
      gain.gain.exponentialRampToValueAtTime(vol, when + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, when + dur);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(when);
      osc.stop(when + dur + 0.03);
    }

    function chime(kind) {
      if (!soundOn || !ctx) return;
      const t = ctx.currentTime;
      if (kind === "ok") {
        tone(523.25, t, 0.12, "sine", 0.05);
        tone(659.25, t + 0.09, 0.14, "sine", 0.05);
        tone(783.99, t + 0.18, 0.2, "sine", 0.045);
      } else if (kind === "no") {
        tone(294, t, 0.12, "triangle", 0.03);
      } else {
        [523, 659, 784, 1046].forEach((freq, i) => tone(freq, t + i * 0.11, 0.18, "sine", 0.05));
      }
    }

    function pickVoice(prefix) {
      if (!window.speechSynthesis) return null;
      const voices = speechSynthesis.getVoices();
      if (prefix === "en") {
        const prefer = ["Daniel", "Kate", "Serena", "Samantha", "Karen", "Moira", "Google UK English", "Google US English"];
        for (const name of prefer) {
          const voice = voices.find((item) => item.lang && item.lang.toLowerCase().startsWith("en") && item.name.includes(name));
          if (voice) return voice;
        }
        return voices.find((item) => item.lang && item.lang.toLowerCase().startsWith("en")) || null;
      }
      return voices.find((item) => /zh[-_]HK|zh[-_]TW|Sinji|Meijia/i.test(`${item.lang} ${item.name}`))
        || voices.find((item) => item.lang && item.lang.toLowerCase().startsWith("zh"))
        || null;
    }

    function clearSpeech() {
      queue = [];
      speaking = false;
      if (window.speechSynthesis) speechSynthesis.cancel();
    }

    function pump() {
      if (!queue.length) {
        speaking = false;
        return;
      }
      if (!window.speechSynthesis) {
        queue = [];
        speaking = false;
        return;
      }
      speaking = true;
      const item = queue.shift();
      const utter = new SpeechSynthesisUtterance(item.text);
      utter.lang = item.lang;
      utter.rate = item.rate || 0.9;
      utter.pitch = 1.04;
      const voice = pickVoice(item.lang.startsWith("zh") ? "zh" : "en");
      if (voice) utter.voice = voice;
      utter.onend = () => { speaking = false; pump(); };
      utter.onerror = () => { speaking = false; pump(); };
      speechSynthesis.speak(utter);
    }

    function speak(text, lang, rate) {
      if (!soundOn || !text) return;
      queue.push({ text, lang: lang || "en-GB", rate });
      if (speaking) return;
      speaking = true;
      setTimeout(pump, 60);
    }

    function setSound(on) { soundOn = !!on; }

    if (window.speechSynthesis) {
      speechSynthesis.onvoiceschanged = () => speechSynthesis.getVoices();
      speechSynthesis.getVoices();
    }

    return { setup, chime, speak, clearSpeech, setSound };
  }

  function bindPress(root) {
    const scope = root || document;
    scope.addEventListener("pointerdown", (event) => {
      const btn = event.target.closest("button");
      if (btn) btn.classList.add("down");
    });
    const clear = () => scope.querySelectorAll(".down").forEach((node) => node.classList.remove("down"));
    scope.addEventListener("pointerup", clear);
    scope.addEventListener("pointercancel", clear);
  }

  function makeShell(options) {
    const state = load(options.key, options.defaultState);
    const audio = createAudio();
    audio.setSound(state.sound !== false);
    let timers = [];
    let roundId = 0;

    function later(fn, ms) {
      const id = setTimeout(fn, ms);
      timers.push(id);
      return id;
    }

    function clearTimers() {
      timers.forEach(clearTimeout);
      timers = [];
    }

    function show(id) {
      document.querySelectorAll(".screen").forEach((node) => {
        node.classList.toggle("on", node.id === id);
      });
    }

    function persist() { save(options.key, state); }

    function bumpRound() {
      roundId += 1;
      return roundId;
    }

    function isCurrent(id) { return id === roundId; }

    return {
      state,
      audio,
      later,
      clearTimers,
      show,
      persist,
      bumpRound,
      isCurrent,
      get roundId() { return roundId; }
    };
  }

  global.DinoShared = {
    INK,
    DINOS,
    svg,
    drawDino,
    worldSvg,
    homeIcon,
    starHtml,
    trailHtml,
    shuffle,
    load,
    save,
    createAudio,
    bindPress,
    makeShell
  };
})(window);
