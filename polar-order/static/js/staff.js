(() => {
  const pin = window.POLAR_PIN;
  const box = document.getElementById("orders");
  const livePill = document.getElementById("livePill");
  let audioCtx = null;

  function beep() {
    try {
      audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const o = audioCtx.createOscillator();
      const g = audioCtx.createGain();
      o.connect(g);
      g.connect(audioCtx.destination);
      o.frequency.value = 880;
      g.gain.value = 0.05;
      o.start();
      setTimeout(() => o.stop(), 180);
    } catch (_) {}
  }

  function money(n) {
    return `$${Math.round(Number(n))}`;
  }

  function render(orders) {
    if (!orders.length) {
      box.innerHTML = `<div class="card muted">No open orders.</div>`;
      return;
    }
    box.innerHTML = orders
      .map((o) => {
        const items = o.items
          .map(
            (i) => `
          <div class="cart-line">
            <div>
              <strong>${i.qty}× ${i.item_name}</strong>
              ${i.note ? `<div class="muted">${i.note}</div>` : ""}
            </div>
            <div>${money(i.line_total)}</div>
          </div>`
          )
          .join("");
        return `
        <article class="card ${o.status}">
          <div class="row">
            <div>
              <strong>${o.table_label}</strong>
              <div class="muted">#${o.id}</div>
            </div>
            <span class="badge ${o.status}">${o.status}</span>
          </div>
          ${o.note ? `<p class="muted">${o.note}</p>` : ""}
          ${items}
          <div class="actions">
            ${
              o.status === "new"
                ? `<button class="btn-prep" data-id="${o.id}" data-status="preparing">Preparing</button>`
                : ""
            }
            ${
              o.status === "preparing"
                ? `<button class="btn-ready" data-id="${o.id}" data-status="ready">Ready</button>`
                : ""
            }
            ${
              o.status !== "served"
                ? `<button class="btn-served" data-id="${o.id}" data-status="served">Served</button>`
                : ""
            }
            <button class="btn-cancel" data-id="${o.id}" data-status="cancelled">Cancel</button>
            <a class="ghost" style="width:auto;padding:8px 12px;display:inline-block" href="/staff/bill/${o.table_code}?pin=${encodeURIComponent(pin)}">Bill</a>
          </div>
        </article>`;
      })
      .join("");
  }

  async function load() {
    const res = await fetch(`/api/staff/orders?pin=${encodeURIComponent(pin)}`);
    if (!res.ok) {
      box.innerHTML = `<div class="card">Unauthorized</div>`;
      return;
    }
    render(await res.json());
  }

  box.addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-status]");
    if (!btn) return;
    const fd = new FormData();
    fd.append("status", btn.dataset.status);
    fd.append("pin", pin);
    await fetch(`/api/staff/orders/${btn.dataset.id}/status`, {
      method: "POST",
      body: fd,
    });
    load();
  });

  function connectSSE() {
    const es = new EventSource(`/api/events?pin=${encodeURIComponent(pin)}`);
    es.onopen = () => {
      livePill.textContent = "Live";
    };
    es.onerror = () => {
      livePill.textContent = "Reconnecting…";
    };
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "order.new") {
          beep();
          livePill.textContent = "NEW ORDER";
          setTimeout(() => (livePill.textContent = "Live"), 2500);
        }
        if (msg.type === "order.new" || msg.type === "order.status") load();
      } catch (_) {}
    };
  }

  load();
  connectSSE();
  setInterval(load, 15000);
})();
