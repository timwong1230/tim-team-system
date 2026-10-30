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
        const gift = o.deliver_to_label
          ? `<div class="gift-banner">
              <strong>Treat → ${o.deliver_to_label}</strong>
              <div>From ${o.table_label}${o.guest_name ? ` (${o.guest_name})` : ""}</div>
              ${o.gift_message ? `<div class="gift-msg">“${o.gift_message}”</div>` : ""}
              <div class="muted">Deliver to ${o.deliver_to_label}. Tell them it’s from ${o.table_label}.</div>
            </div>`
          : "";
        return `
        <article class="card ${o.status}${o.deliver_to_label ? " gift-order" : ""}">
          <div class="row">
            <div>
              <strong>${o.deliver_to_label ? `${o.table_label} → ${o.deliver_to_label}` : o.table_label}</strong>
              <div class="muted">#${o.id}${o.guest_name ? ` · ${o.guest_name}` : ""}${o.created_by ? ` · by ${o.created_by}` : ""}</div>
            </div>
            <span class="badge ${o.status}">${o.status}</span>
          </div>
          ${gift}
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
              o.status === "served"
                ? `<button class="btn-undo" data-id="${o.id}" data-status="ready">Undo served</button>`
                : `<button class="btn-served" data-id="${o.id}" data-status="served">Served</button>`
            }
            <button class="btn-cancel" data-id="${o.id}" data-status="cancelled">Cancel</button>
            <a class="ghost" style="width:auto;padding:8px 12px;display:inline-block" href="/staff/bill/${o.table_code}?pin=${encodeURIComponent(pin)}">Bill</a>
            <a class="ghost" style="width:auto;padding:8px 12px;display:inline-block" href="/staff/order/${o.table_code}?pin=${encodeURIComponent(pin)}">Add / fix</a>
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
    const next = btn.dataset.status;
    if (next === "cancelled" && !confirm("Cancel this order?")) return;
    if (next === "ready" && btn.classList.contains("btn-undo")) {
      if (!confirm("Undo served so you can fix / cancel this order?")) return;
    }
    const fd = new FormData();
    fd.append("status", next);
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
