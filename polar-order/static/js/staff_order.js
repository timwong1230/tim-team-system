document.addEventListener("DOMContentLoaded", () => {
  const cfg = window.POLAR_STAFF_ORDER || {};
  const table = cfg.table;
  const pin = cfg.pin;
  const cart = new Map();
  const cartBar = document.getElementById("cartBar");
  const cartCount = document.getElementById("cartCount");
  const cartTotal = document.getElementById("cartTotal");
  const drawer = document.getElementById("drawer");
  const cartLines = document.getElementById("cartLines");
  const toast = document.getElementById("toast");

  function showToast(msg) {
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2200);
  }

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
        addCartLine({
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
    addCartLine({
      ...item,
      serveChoice: choice,
      serveKind: serve.kind,
      servePrefix: prefixForServeChoice(choice, serve.kind),
    });
    closeServePicker();
  });

  function addCartLine(item) {
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

  document.getElementById("nomAdd")?.addEventListener("click", () => {
    const name = (document.getElementById("nomName")?.value || "").trim();
    const price = Number(document.getElementById("nomPrice")?.value);
    const qty = Math.max(1, Number(document.getElementById("nomQty")?.value || 1));
    if (!name) return showToast("Enter product name");
    if (Number.isNaN(price) || price < 0) return showToast("Enter a valid price");
    const id = `nom-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-").slice(0, 40)}`;
    const existing = cart.get(id);
    if (existing) existing.qty += qty;
    else {
      cart.set(id, {
        id,
        name,
        price,
        listPrice: price,
        promoType: "",
        comboPrice: null,
        qty,
        note: "",
        allowNote: false,
        custom: true,
        customName: name,
        customPrice: price,
      });
    }
    renderCartBar();
    renderCartLines();
    document.getElementById("nomName").value = "";
    document.getElementById("nomPrice").value = "";
    document.getElementById("nomQty").value = "1";
    showToast("Added");
  });

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
      const options = (card.dataset.serveOptions || "")
        .split("|")
        .map((s) => s.trim())
        .filter(Boolean);
      const payload = {
        id: card.dataset.id,
        itemId: card.dataset.id,
        name: card.dataset.name,
        price: Number(card.dataset.price),
        listPrice: Number(card.dataset.listPrice || card.dataset.price),
        promoType: card.dataset.promoType || "",
        comboPrice: card.dataset.comboPrice ? Number(card.dataset.comboPrice) : null,
        qty: 1,
        note: "",
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
      addCartLine(payload);
    });
  });

  document.getElementById("openCart").addEventListener("click", () => {
    renderCartLines();
    drawer.classList.add("open");
  });
  document.getElementById("closeCart").addEventListener("click", () => {
    drawer.classList.remove("open");
  });
  drawer.addEventListener("click", (e) => {
    if (e.target === drawer) drawer.classList.remove("open");
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

  document.getElementById("submitOrder").addEventListener("click", async () => {
    if (!cart.size) return showToast("Cart is empty");
    const payload = {
      pin,
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
    if (cfg.needsCheckin) {
      payload.guest_name = (document.getElementById("staffGuestName")?.value || "").trim() || "Walk-in";
      payload.party_size = Math.max(
        1,
        Number(document.getElementById("staffPartySize")?.value || 2)
      );
    }
    const btn = document.getElementById("submitOrder");
    btn.disabled = true;
    btn.textContent = "Sending…";
    try {
      const res = await fetch(`/api/staff/bill/${table}/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      cart.clear();
      renderCartBar();
      drawer.classList.remove("open");
      showToast("Order sent for table");
      // After first order, check-in is done — reload so header shows guest
      if (cfg.needsCheckin) {
        setTimeout(() => {
          location.href = `/staff/order/${table}?pin=${encodeURIComponent(pin)}`;
        }, 600);
      }
    } catch (err) {
      showToast("Failed to send order");
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Send order for table";
    }
  });
});
