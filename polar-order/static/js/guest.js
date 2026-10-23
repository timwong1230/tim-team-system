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

  function serveSlug(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  const GLASS_STYLES = new Set(["Neat", "On the Rocks"]);

  function prefixForServeChoice(choice, kind) {
    if (kind === "mixer") return "Mixer";
    if (kind === "single_mix") return "Spirit";
    if (GLASS_STYLES.has(choice)) return "Serve";
    return "Mixer";
  }

  function lineNotePayload(line) {
    const parts = [];
    if (line.serveKind === "single_mix" && line.serveSpirit && line.serveMixer) {
      parts.push(`Spirit: ${line.serveSpirit}`);
      parts.push(`Mixer: ${line.serveMixer}`);
    } else if (line.serveChoice) {
      const prefix =
        line.servePrefix || prefixForServeChoice(line.serveChoice, line.serveKind);
      parts.push(`${prefix}: ${line.serveChoice}`);
    }
    if (line.note) parts.push(line.note);
    return parts.length ? parts.join(" · ") : null;
  }

  const serveDrawer = document.getElementById("serveDrawer");
  const serveChoices = document.getElementById("serveChoices");
  const serveItemName = document.getElementById("serveItemName");
  const serveDrawerTitle = document.getElementById("serveDrawerTitle");
  let pendingServeItem = null;

  function renderServeOptions(options, dataAttr) {
    if (!serveChoices) return;
    serveChoices.innerHTML = options
      .map((m) => {
        const label = typeof m === "string" ? m : m.label || m.name;
        const value = typeof m === "string" ? m : m.name;
        return `<button type="button" class="mixer-choice" data-${dataAttr}="${String(value).replace(/"/g, "&quot;")}">${label}</button>`;
      })
      .join("");
  }

  function openServePicker(item, serve) {
    pendingServeItem = { item, serve, step: serve.kind === "single_mix" ? "spirit" : "choice" };
    if (serveDrawerTitle) serveDrawerTitle.textContent = serve.title || "Choose option";
    if (serveItemName) {
      serveItemName.textContent =
        serve.kind === "single_mix" ? "1/2 — Pick house spirit" : item.name;
    }
    if (serve.kind === "single_mix") {
      const spirits = window.POLAR_SINGLE_MIX_SPIRITS || [];
      renderServeOptions(spirits, "spirit");
    } else {
      renderServeOptions(serve.options || [], "serve");
    }
    serveDrawer?.classList.add("open");
  }

  function closeServePicker() {
    pendingServeItem = null;
    serveDrawer?.classList.remove("open");
  }

  document.getElementById("closeServe")?.addEventListener("click", closeServePicker);
  serveDrawer?.addEventListener("click", (e) => {
    if (e.target === serveDrawer) closeServePicker();
  });
  serveChoices?.addEventListener("click", (e) => {
    if (!pendingServeItem) return;
    const { item, serve } = pendingServeItem;
    if (serve.kind === "single_mix") {
      const spiritBtn = e.target.closest("[data-spirit]");
      const mixerBtn = e.target.closest("[data-mixer]");
      if (spiritBtn && pendingServeItem.step === "spirit") {
        pendingServeItem.spirit = spiritBtn.dataset.spirit;
        pendingServeItem.step = "mixer";
        if (serveDrawerTitle) serveDrawerTitle.textContent = "Choose mixer";
        if (serveItemName) {
          serveItemName.textContent = `2/2 — ${pendingServeItem.spirit} · pick mixer`;
        }
        renderServeOptions(serve.mixers || [], "mixer");
        return;
      }
      if (mixerBtn && pendingServeItem.step === "mixer" && pendingServeItem.spirit) {
        const mixer = mixerBtn.dataset.mixer;
        const spirit = pendingServeItem.spirit;
        addToCart({
          ...item,
          serveKind: "single_mix",
          serveSpirit: spirit,
          serveMixer: mixer,
          serveChoice: `${spirit} + ${mixer}`,
          servePrefix: "Spirit",
        });
        closeServePicker();
      }
      return;
    }
    const btn = e.target.closest("[data-serve]");
    if (!btn) return;
    const choice = btn.dataset.serve;
    addToCart({
      ...item,
      serveChoice: choice,
      serveKind: serve.kind,
      servePrefix: prefixForServeChoice(choice, serve.kind),
    });
    closeServePicker();
  });

  function addToCart(item) {
    const itemId = item.itemId || item.id;
    const serveChoice = item.serveChoice || "";
    const id = serveChoice ? `${itemId}__${serveSlug(serveChoice)}` : itemId;
    const existing = cart.get(id);
    if (existing) {
      existing.qty += item.qty || 1;
    } else {
      cart.set(id, {
        id,
        itemId,
        name: item.name,
        price: Number(item.price),
        listPrice: Number(item.listPrice || item.price),
        promoType: item.promoType || "",
        comboPrice: item.comboPrice != null ? Number(item.comboPrice) : null,
        qty: item.qty || 1,
        note: item.note || "",
        allowNote: !!item.allowNote,
        serveChoice: serveChoice || null,
        serveKind: item.serveKind || null,
        servePrefix: item.servePrefix || null,
        serveSpirit: item.serveSpirit || null,
        serveMixer: item.serveMixer || null,
        custom: !!item.custom,
        customName: item.customName || null,
        customPrice: item.customPrice != null ? Number(item.customPrice) : null,
      });
    }
    renderCartBar();
    showToast(serveChoice ? `Added · ${serveChoice}` : "Added");
  }

  function pricedCart() {
    let shishaSlots = 0;
    for (const line of cart.values()) {
      if ((line.itemId || line.id) === "shisha-regular") shishaSlots += line.qty;
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
      const serveNote = line.serveKind === "single_mix" && line.serveSpirit
        ? `<div class="muted">Spirit: ${line.serveSpirit}<br/>Mixer: ${line.serveMixer || ""}</div>`
        : line.serveChoice
          ? `<div class="muted">${line.servePrefix || prefixForServeChoice(line.serveChoice, line.serveKind)}: ${line.serveChoice}</div>`
          : "";
      row.innerHTML = `
        <div>
          <strong>${line.name}</strong>
          ${nomNote}
          ${serveNote}
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

  const catHub = document.getElementById("catHub");
  const subHubs = Array.from(document.querySelectorAll(".cat-subhub"));
  const productSections = Array.from(document.querySelectorAll(".section-products"));

  function hideAllNavPanels() {
    if (catHub) catHub.hidden = true;
    subHubs.forEach((hub) => {
      hub.hidden = true;
    });
    productSections.forEach((sec) => {
      sec.hidden = true;
    });
    document.querySelectorAll(".cat-btn").forEach((b) => b.classList.remove("active"));
  }

  function showRootHub() {
    hideAllNavPanels();
    if (catHub) catHub.hidden = false;
    catHub?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openSubHub(groupId) {
    const hub = document.getElementById(`sub-${groupId}`);
    if (!hub) return;
    hideAllNavPanels();
    hub.hidden = false;
    document.querySelectorAll(`.cat-btn[data-group="${groupId}"]`).forEach((b) => {
      b.classList.add("active");
    });
    hub.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function openLeaf(targetId) {
    const section = document.getElementById(targetId);
    if (!section) return;
    hideAllNavPanels();
    section.hidden = false;
    document.querySelectorAll(`.cat-btn[data-target="${targetId}"]`).forEach((b) => {
      b.classList.add("active");
    });
    section.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  document.querySelectorAll(".cat-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.navKind === "group" && btn.dataset.group) {
        openSubHub(btn.dataset.group);
        return;
      }
      if (btn.dataset.target) openLeaf(btn.dataset.target);
    });
  });

  document.querySelectorAll("[data-nav-back]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.navBack;
      if (mode === "sub" && btn.dataset.parent) {
        openSubHub(btn.dataset.parent);
        return;
      }
      showRootHub();
    });
  });

  document.querySelectorAll(".item .add-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".item");
      const options = (card.dataset.serveOptions || "")
        .split("|")
        .map((s) => s.trim())
        .filter(Boolean);
      const payload = {
        id: card.dataset.id,
        itemId: card.dataset.id,
        name: card.dataset.name,
        price: card.dataset.price,
        listPrice: card.dataset.listPrice || card.dataset.price,
        promoType: card.dataset.promoType || "",
        comboPrice: card.dataset.comboPrice || null,
        allowNote: card.dataset.allowNote === "1",
      };
      const kind = card.dataset.serveKind || "";
      if (kind === "single_mix") {
        openServePicker(payload, {
          kind: "single_mix",
          title: card.dataset.serveTitle || "Single Mix",
          mixers: (card.dataset.serveMixers || "")
            .split("|")
            .map((s) => s.trim())
            .filter(Boolean),
        });
        return;
      }
      if (options.length) {
        openServePicker(payload, {
          kind: kind || "glass",
          title: card.dataset.serveTitle || "Choose option",
          prefix: card.dataset.servePrefix || "Serve",
          options,
        });
        return;
      }
      addToCart(payload);
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
    window.POLAR_TABLE_LABEL ||
    document.getElementById("tablePill")?.textContent?.trim() ||
    "your table";

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
      submitBtn.textContent = treating ? "Send treat" : "Send Order";
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
          item_id: l.itemId || l.id,
          qty: l.qty,
          note: lineNotePayload(l),
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
