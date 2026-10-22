document.addEventListener("DOMContentLoaded", () => {
  const table = window.POLAR_TABLE;
  const toast = document.getElementById("toast");

  function showToast(msg) {
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2200);
  }

  // Welcome: name → party size
  if (!window.POLAR_READY) {
    const nameInput = document.getElementById("guestName");
    const partyInput = document.getElementById("partySize");
    const stepName = document.getElementById("stepName");
    const stepParty = document.getElementById("stepParty");
    const hello = document.getElementById("welcomeHello");

    document.getElementById("toParty")?.addEventListener("click", () => {
      const name = (nameInput.value || "").trim();
      if (!name) {
        showToast("Please enter a name");
        nameInput.focus();
        return;
      }
      hello.textContent = `Hi ${name}`;
      stepName.hidden = true;
      stepParty.hidden = false;
      partyInput.focus();
    });

    document.getElementById("backName")?.addEventListener("click", () => {
      stepParty.hidden = true;
      stepName.hidden = false;
      nameInput.focus();
    });

    document.getElementById("startOrder")?.addEventListener("click", async () => {
      const guest_name = (nameInput.value || "").trim();
      const party_size = Number(partyInput.value || 1);
      if (!guest_name) {
        showToast("Please enter a name");
        return;
      }
      const btn = document.getElementById("startOrder");
      btn.disabled = true;
      btn.textContent = "Opening…";
      try {
        const res = await fetch(`/api/t/${table}/welcome`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ guest_name, party_size }),
        });
        if (!res.ok) throw new Error(await res.text());
        location.reload();
      } catch (err) {
        console.error(err);
        showToast("Could not start — try again");
        btn.disabled = false;
        btn.textContent = "Start ordering";
      }
    });

    nameInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        document.getElementById("toParty")?.click();
      }
    });
    return;
  }

  const cart = new Map();
  const cartBar = document.getElementById("cartBar");
  const cartCount = document.getElementById("cartCount");
  const cartTotal = document.getElementById("cartTotal");
  const drawer = document.getElementById("drawer");
  const cartLines = document.getElementById("cartLines");
  const giftToggle = document.getElementById("giftToggle");
  const giftFields = document.getElementById("giftFields");
  const giftSeat = document.getElementById("giftSeat");
  const giftMessage = document.getElementById("giftMessage");
  const aiDrawer = document.getElementById("aiDrawer");
  const aiThread = document.getElementById("aiThread");
  const aiForm = document.getElementById("aiForm");
  const aiInput = document.getElementById("aiInput");
  const aiHistory = [];
  const viewOrderDrawer = document.getElementById("viewOrderDrawer");
  const viewOrderLines = document.getElementById("viewOrderLines");
  const openViewOrderBtn = document.getElementById("openViewOrder");

  if (!cartBar || !drawer) return;

  function money(n) {
    return `$${Math.round(n)}`;
  }

  function addToCart(item) {
    const id = item.id;
    const existing = cart.get(id);
    if (existing) {
      existing.qty += item.qty || 1;
    } else {
      cart.set(id, {
        id,
        name: item.name,
        price: Number(item.price),
        listPrice: Number(item.listPrice || item.price),
        promoType: item.promoType || "",
        comboPrice: item.comboPrice != null ? Number(item.comboPrice) : null,
        qty: item.qty || 1,
        note: item.note || "",
        allowNote: !!item.allowNote,
        custom: !!item.custom,
        customName: item.customName || null,
        customPrice: item.customPrice != null ? Number(item.customPrice) : null,
      });
    }
    renderCartBar();
    showToast("Added");
  }

  function pricedCart() {
    let shishaSlots = 0;
    for (const line of cart.values()) {
      if (line.id === "shisha-regular") shishaSlots += line.qty;
    }
    const out = [];
    for (const line of cart.values()) {
      if (line.promoType !== "snacks") {
        out.push({
          ...line,
          unitPrice: line.price,
          lineTotal: line.qty * line.price,
          comboQty: 0,
        });
        continue;
      }
      const comboPrice = Number(line.comboPrice || 40);
      const comboQty = Math.min(line.qty, shishaSlots);
      shishaSlots -= comboQty;
      const fullQty = line.qty - comboQty;
      const listPrice = Number(line.listPrice || line.price);
      const lineTotal = comboQty * comboPrice + fullQty * listPrice;
      out.push({
        ...line,
        unitPrice: comboQty === line.qty ? comboPrice : listPrice,
        lineTotal,
        comboQty,
      });
    }
    return out;
  }

  function renderCartBar() {
    const lines = pricedCart();
    let qty = 0;
    let total = 0;
    for (const line of lines) {
      qty += line.qty;
      total += line.lineTotal;
    }
    if (!qty) {
      cartBar.style.display = "none";
      return;
    }
    cartBar.style.display = "flex";
    cartCount.textContent = `${qty} item${qty > 1 ? "s" : ""}`;
    cartTotal.textContent = money(total);
  }

  function renderCartLines() {
    cartLines.innerHTML = "";
    const lines = pricedCart();
    if (!lines.length) {
      cartLines.innerHTML = `<p class="muted">Cart is empty.</p>`;
      return;
    }
    for (const line of lines) {
      const row = document.createElement("div");
      row.className = "cart-line";
      const comboNote =
        line.comboQty > 0
          ? `<div class="muted">${line.comboQty}× Shisha combo $40</div>`
          : "";
      const nomNote = line.custom ? `<div class="muted">Not on Menu</div>` : "";
      row.innerHTML = `
        <div>
          <strong>${line.name}</strong>
          ${nomNote}
          ${comboNote}
          <div class="qty">
            <button type="button" data-act="dec" data-id="${line.id}">−</button>
            <span>${line.qty}</span>
            <button type="button" data-act="inc" data-id="${line.id}">+</button>
          </div>
          ${
            line.allowNote
              ? `<input class="field" style="margin-top:8px" data-note="${line.id}" placeholder="Flavour / note" value="${line.note || ""}" />`
              : ""
          }
        </div>
        <div>${money(line.lineTotal)}</div>
      `;
      cartLines.appendChild(row);
    }
  }

  document.querySelectorAll(".cat-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".cat-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const el = document.getElementById(btn.dataset.target);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  document.querySelectorAll(".item .add-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".item");
      addToCart({
        id: card.dataset.id,
        name: card.dataset.name,
        price: card.dataset.price,
        listPrice: card.dataset.listPrice || card.dataset.price,
        promoType: card.dataset.promoType || "",
        comboPrice: card.dataset.comboPrice || null,
        allowNote: card.dataset.allowNote === "1",
      });
    });
  });

  document.getElementById("openCart").addEventListener("click", () => {
    resetGiftToOwnTable();
    renderCartLines();
    drawer.classList.add("open");
  });
  document.getElementById("closeCart").addEventListener("click", () => {
    drawer.classList.remove("open");
  });
  drawer.addEventListener("click", (e) => {
    if (e.target === drawer) drawer.classList.remove("open");
  });

  const submitBtn = document.getElementById("submitOrder");
  const orderTargetHint = document.getElementById("orderTargetHint");
  const ownTableLabel =
    document.querySelector(".pill")?.textContent?.trim() || "your table";

  function resetGiftToOwnTable() {
    if (!giftToggle) return;
    giftToggle.checked = false;
    if (giftFields) giftFields.hidden = true;
    if (giftSeat) giftSeat.value = "";
    if (giftMessage) giftMessage.value = "";
    syncOrderTargetUI();
  }

  function syncOrderTargetUI() {
    const treating = !!(giftToggle && giftToggle.checked);
    if (giftFields) giftFields.hidden = !treating;
    if (orderTargetHint) {
      if (treating && giftSeat?.value) {
        const label = giftSeat.selectedOptions[0]?.textContent || giftSeat.value;
        orderTargetHint.innerHTML = `Treat for <strong>${label}</strong> · bill on <strong>${ownTableLabel}</strong>.`;
      } else if (treating) {
        orderTargetHint.innerHTML = `Pick a seat to treat · bill stays on <strong>${ownTableLabel}</strong>.`;
      } else {
        orderTargetHint.innerHTML = `Sending to <strong>${ownTableLabel}</strong> (your table).`;
      }
    }
    if (submitBtn) {
      submitBtn.textContent = treating ? "Send treat" : `Send to ${ownTableLabel}`;
    }
  }

  giftToggle?.addEventListener("change", syncOrderTargetUI);
  giftSeat?.addEventListener("change", syncOrderTargetUI);

  document.getElementById("jumpGift")?.addEventListener("click", () => {
    if (!cart.size) {
      showToast("Add something first");
      return;
    }
    renderCartLines();
    drawer.classList.add("open");
    // Shortcut: open cart with treat option ready — still requires manual seat + message
    if (giftToggle) {
      giftToggle.checked = true;
      syncOrderTargetUI();
      giftSeat?.focus();
    }
  });

  cartLines.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const line = cart.get(btn.dataset.id);
    if (!line) return;
    if (btn.dataset.act === "inc") line.qty += 1;
    if (btn.dataset.act === "dec") {
      line.qty -= 1;
      if (line.qty <= 0) cart.delete(line.id);
    }
    renderCartLines();
    renderCartBar();
  });

  cartLines.addEventListener("input", (e) => {
    const input = e.target.closest("input[data-note]");
    if (!input) return;
    const line = cart.get(input.dataset.note);
    if (line) line.note = input.value;
  });

  submitBtn?.addEventListener("click", async () => {
    if (!cart.size) return showToast("Cart is empty");
    const payload = {
      note: document.getElementById("orderNote").value || null,
      items: [...cart.values()].map((l) => {
        if (l.custom) {
          return {
            item_id: "not-on-menu",
            qty: l.qty,
            note: l.note || null,
            custom_name: l.customName || l.name,
            custom_price: l.customPrice != null ? l.customPrice : l.price,
          };
        }
        return {
          item_id: l.id,
          qty: l.qty,
          note: l.note || null,
        };
      }),
    };
    // Default = own table. Only attach deliver_to when guest ticks the box.
    if (giftToggle?.checked) {
      const seat = (giftSeat?.value || "").trim();
      const msg = (giftMessage?.value || "").trim();
      if (!seat) return showToast("Pick who to treat");
      if (!msg) return showToast("Add a message for them");
      payload.deliver_to = seat;
      payload.gift_message = msg;
    }
    const btn = submitBtn;
    btn.disabled = true;
    const prevLabel = btn.textContent;
    btn.textContent = "Sending…";
    try {
      const res = await fetch(`/api/t/${table}/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      cart.clear();
      renderCartBar();
      drawer.classList.remove("open");
      resetGiftToOwnTable();
      showToast(payload.deliver_to ? "Treat sent" : `Sent to ${ownTableLabel}`);
      // Refresh View Order quietly so the list is ready
      loadViewOrder({ silent: true });
    } catch (err) {
      showToast("Failed to send order");
      console.error(err);
      btn.textContent = prevLabel;
    } finally {
      btn.disabled = false;
      if (!payload.deliver_to) syncOrderTargetUI();
    }
  });

  resetGiftToOwnTable();

  // —— View Order (sent items, no prices) ——
  async function loadViewOrder({ silent } = {}) {
    if (!viewOrderLines) return;
    if (!silent) {
      viewOrderLines.innerHTML = `<p class="muted">Loading…</p>`;
    }
    try {
      const res = await fetch(`/api/t/${table}/my-orders`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const items = data.items || [];
      if (!items.length) {
        viewOrderLines.innerHTML = `<p class="muted">Nothing sent yet. Add items to your cart and tap Send.</p>`;
        return;
      }
      viewOrderLines.innerHTML = items
        .map(
          (it) => `
        <div class="view-order-line">
          <span class="view-order-qty">${it.qty}×</span>
          <span class="view-order-name">${String(it.name).replace(/</g, "&lt;")}</span>
        </div>`
        )
        .join("");
    } catch (err) {
      console.error(err);
      if (!silent) {
        viewOrderLines.innerHTML = `<p class="muted">Could not load your order.</p>`;
        showToast("Could not load View Order");
      }
    }
  }

  openViewOrderBtn?.addEventListener("click", () => {
    viewOrderDrawer?.classList.add("open");
    loadViewOrder();
  });
  document.getElementById("closeViewOrder")?.addEventListener("click", () => {
    viewOrderDrawer?.classList.remove("open");
  });
  viewOrderDrawer?.addEventListener("click", (e) => {
    if (e.target === viewOrderDrawer) viewOrderDrawer.classList.remove("open");
  });

  // —— Ask AI ——
  function appendAI(role, html) {
    const bubble = document.createElement("div");
    bubble.className = `ai-bubble ai-${role}`;
    bubble.innerHTML = html;
    aiThread.appendChild(bubble);
    aiThread.scrollTop = aiThread.scrollHeight;
  }

  function renderSuggestions(list) {
    if (!list?.length) return "";
    return `<div class="ai-suggest">${list
      .map(
        (s) => `
      <button type="button" class="ai-suggest-btn"
        data-id="${s.item_id}"
        data-name="${s.name.replace(/"/g, "&quot;")}"
        data-price="${s.price}">
        <strong>${s.name}</strong>
        <span>$${Math.round(s.price)}</span>
        ${s.why ? `<em>${s.why}</em>` : ""}
        <span class="ai-add">Add</span>
      </button>`
      )
      .join("")}</div>`;
  }

  async function askAI(message) {
    const text = (message || "").trim();
    if (!text) return;
    appendAI("user", text.replace(/</g, "&lt;"));
    aiHistory.push({ role: "user", content: text });
    aiInput.value = "";
    const sendBtn = document.getElementById("aiSend");
    sendBtn.disabled = true;
    sendBtn.textContent = "…";
    try {
      const res = await fetch(`/api/t/${table}/ask-ai`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: aiHistory.slice(0, -1) }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      const reply = (data.reply || "").replace(/</g, "&lt;").replace(/\n/g, "<br>");
      appendAI("bot", reply + renderSuggestions(data.suggestions || []));
      aiHistory.push({ role: "assistant", content: data.reply || "" });
    } catch (err) {
      console.error(err);
      appendAI("bot", "Hmm, I glitched — try again in a sec.");
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = "Ask";
    }
  }

  document.getElementById("openAskAI")?.addEventListener("click", () => {
    aiDrawer.classList.add("open");
    if (!aiThread.childElementCount) {
      appendAI(
        "bot",
        `Hey ${window.POLAR_GUEST || "there"} — what mood are we in tonight?`
      );
    }
    aiInput.focus();
  });
  document.getElementById("closeAskAI")?.addEventListener("click", () => {
    aiDrawer.classList.remove("open");
  });
  aiDrawer?.addEventListener("click", (e) => {
    if (e.target === aiDrawer) aiDrawer.classList.remove("open");
  });
  document.querySelectorAll(".ai-chip").forEach((chip) => {
    chip.addEventListener("click", () => askAI(chip.dataset.q));
  });
  aiForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    askAI(aiInput.value);
  });
  aiThread?.addEventListener("click", (e) => {
    const btn = e.target.closest(".ai-suggest-btn");
    if (!btn) return;
    // look up promo attrs from menu card if present
    const card = document.querySelector(`.item[data-id="${btn.dataset.id}"]`);
    addToCart({
      id: btn.dataset.id,
      name: btn.dataset.name,
      price: card?.dataset.price || btn.dataset.price,
      listPrice: card?.dataset.listPrice || btn.dataset.price,
      promoType: card?.dataset.promoType || "",
      comboPrice: card?.dataset.comboPrice || null,
      allowNote: card?.dataset.allowNote === "1",
    });
  });
});
