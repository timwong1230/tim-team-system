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
    if (kind === "birthday") return "Promo";
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
    if (serve.kind === "birthday") {
      const alreadyFree = [...cart.values()].some(
        (l) => l.serveKind === "birthday" && l.serveChoice === "Birthday Free"
      );
      if (choice === "Birthday Free" && alreadyFree) {
        showToast("Only one Birthday Free cocktail per table");
        closeServePicker();
        return;
      }
      addCartLine({
        ...item,
        price: choice === "Birthday Free" ? 0 : item.price,
        serveChoice: choice,
        serveKind: "birthday",
        servePrefix: "Promo",
      });
      closeServePicker();
      return;
    }
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
    // Note items (e.g. Regular Shisha): never merge — flavour is typed after add,
    // and merging used to drop the second flavour / look like a missing item.
    const id = item.allowNote
      ? `${itemId}__n${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
      : serveChoice
        ? `${itemId}__${serveSlug(serveChoice)}`
        : itemId;
    const existing = !item.allowNote ? cart.get(id) : null;
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
    // Always show the bar so staff can open the cart / Not on Menu as the first item
    // without ordering a menu product first.
    if (cartBar) cartBar.style.display = "flex";
    const openBtn = document.getElementById("openCart");
    if (!qty) {
      if (cartCount) cartCount.textContent = "0 items";
      if (cartTotal) cartTotal.textContent = money(0);
      if (openBtn) openBtn.textContent = "Not on Menu";
      return;
    }
    if (cartCount) cartCount.textContent = `${qty} item${qty > 1 ? "s" : ""}`;
    if (cartTotal) cartTotal.textContent = money(total);
    if (openBtn) openBtn.textContent = "View cart";
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
            <button type="button" data-act="dec" data-id="${line.id}" aria-label="Decrease qty">−</button>
            <input
              class="qty-input"
              type="text"
              inputmode="numeric"
              pattern="[0-9]*"
              enterkeyhint="done"
              data-qty="${line.id}"
              value="${line.qty}"
              aria-label="Quantity"
            />
            <button type="button" data-act="inc" data-id="${line.id}" aria-label="Increase qty">+</button>
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

  const staffSections = Array.from(document.querySelectorAll("#staffOrderMain .section-products"));
  const staffMain = document.getElementById("staffOrderMain");

  function setStaffSectionHidden(el, hide) {
    if (!el) return;
    el.hidden = hide;
    el.classList.toggle("is-nav-hidden", hide);
    el.style.display = hide ? "none" : "";
  }

  function openStaffCategory(targetId, { scroll = true } = {}) {
    const section = document.getElementById(targetId);
    if (!section) return;
    staffSections.forEach((sec) => setStaffSectionHidden(sec, sec !== section));
    document.querySelectorAll("#cats .cat-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.target === targetId);
    });
    if (scroll) {
      try {
        staffMain?.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch (_) {
        staffMain?.scrollIntoView(true);
      }
    }
  }

  document.querySelectorAll("#cats .cat-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      openStaffCategory(btn.dataset.target);
    });
  });

  // First category (usually Shisha) is already visible in HTML; keep rail + panel in sync.
  const firstCat = document.querySelector("#cats .cat-btn.active") || document.querySelector("#cats .cat-btn");
  if (firstCat) openStaffCategory(firstCat.dataset.target, { scroll: false });

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

  function parseQtyRaw(raw, { emptyAs = null, min = 1, max = 99 } = {}) {
    const trimmed = String(raw ?? "").trim();
    if (trimmed === "") return emptyAs;
    const n = Math.floor(Number(trimmed));
    if (!Number.isFinite(n)) return emptyAs;
    if (n <= 0) return 0;
    return Math.min(max, Math.max(min, n));
  }

  function applyCartQty(lineId, raw) {
    const line = cart.get(lineId);
    if (!line) return;
    // Empty → keep at least 1; explicit 0 removes the line.
    const n = parseQtyRaw(raw, { emptyAs: Math.max(1, line.qty || 1), min: 1, max: 99 });
    if (n === 0) {
      cart.delete(lineId);
    } else {
      line.qty = n;
    }
    renderCartLines();
    renderCartBar();
  }

  function commitQtyInput(qtyInput) {
    if (!qtyInput) return;
    applyCartQty(qtyInput.dataset.qty, qtyInput.value);
  }

  function isCommitKey(e) {
    return e.key === "Enter" || e.key === "Go" || e.key === "Done" || e.keyCode === 13;
  }

  cartLines.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    // Sync typed value before +/- so iPad Enter-miss doesn't lose the number.
    const typing = btn.closest(".cart-line")?.querySelector("input[data-qty]");
    if (typing) {
      const typed = parseQtyRaw(typing.value, { emptyAs: null, min: 1, max: 99 });
      if (typed != null && typed > 0) {
        const line = cart.get(btn.dataset.id);
        if (line) line.qty = typed;
      }
    }
    const line = cart.get(btn.dataset.id);
    if (!line) return;
    if (btn.dataset.act === "inc") line.qty = Math.min(99, line.qty + 1);
    if (btn.dataset.act === "dec") {
      line.qty -= 1;
      if (line.qty <= 0) cart.delete(line.id);
    }
    renderCartLines();
    renderCartBar();
  });

  cartLines.addEventListener("input", (e) => {
    const noteInput = e.target.closest("input[data-note]");
    if (noteInput) {
      const line = cart.get(noteInput.dataset.note);
      if (line) line.note = noteInput.value;
      return;
    }
    const qtyInput = e.target.closest("input[data-qty]");
    if (!qtyInput) return;
    // Digits only (text + numeric keypad on iOS/iPad).
    const cleaned = qtyInput.value.replace(/[^\d]/g, "");
    if (cleaned !== qtyInput.value) qtyInput.value = cleaned;
    const line = cart.get(qtyInput.dataset.qty);
    if (!line) return;
    const raw = qtyInput.value.trim();
    // Allow clearing while typing; commit on Enter/blur.
    if (raw === "") return;
    const n = parseQtyRaw(raw, { emptyAs: null, min: 1, max: 99 });
    if (n == null || n < 1) return;
    line.qty = n;
    renderCartBar();
    const totalEl = qtyInput.closest(".cart-line")?.querySelector(":scope > div:last-child");
    if (totalEl) {
      const priced = pricedCart().find((l) => l.id === line.id);
      if (priced) totalEl.textContent = money(priced.lineTotal);
    }
  });

  // blur does not bubble — use capture so iPhone Done / iPad dismiss commits.
  cartLines.addEventListener(
    "blur",
    (e) => {
      const qtyInput = e.target?.matches?.("input[data-qty]") ? e.target : null;
      if (!qtyInput) return;
      commitQtyInput(qtyInput);
    },
    true
  );

  cartLines.addEventListener("change", (e) => {
    const qtyInput = e.target.closest("input[data-qty]");
    if (!qtyInput) return;
    commitQtyInput(qtyInput);
  });

  // Commit on Enter immediately — iPad often does not fire change after Return.
  cartLines.addEventListener("keydown", (e) => {
    const qtyInput = e.target.closest("input[data-qty]");
    if (!qtyInput || !isCommitKey(e)) return;
    e.preventDefault();
    commitQtyInput(qtyInput);
    qtyInput.blur();
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
            qty: Math.min(50, Math.max(1, Number(l.qty) || 1)),
            note: l.note || null,
            custom_name: l.customName || l.name,
            custom_price: l.customPrice != null ? l.customPrice : l.price,
          };
        }
        // Never send compound cart keys (id may include __serve / __note).
        const menuId = l.itemId;
        if (!menuId) throw new Error(`Missing item id for ${l.name || "item"}`);
        return {
          item_id: menuId,
          qty: Math.min(50, Math.max(1, Number(l.qty) || 1)),
          note: lineNotePayload(l),
        };
      }),
    };
    if (cfg.needsCheckin) {
      payload.guest_name = (document.getElementById("staffGuestName")?.value || "").trim() || "Walk-in";
      const partyRaw = (document.getElementById("staffPartySize")?.value || "").trim();
      const partySize = Number(partyRaw);
      if (!partyRaw || Number.isNaN(partySize) || partySize < 1 || partySize > 30) {
        showToast("Enter party size (人數) before opening the table");
        document.getElementById("staffPartySize")?.focus();
        document.getElementById("staffCheckin")?.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      payload.party_size = Math.floor(partySize);
    }
    if (cfg.editSession) payload.edit_session = cfg.editSession;
    const btn = document.getElementById("submitOrder");
    btn.disabled = true;
    btn.textContent = "Sending…";
    try {
      const res = await fetch(`/api/staff/bill/${table}/orders`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let detail = "Failed to send order";
        try {
          const errBody = await res.json();
          if (errBody && errBody.detail) detail = errBody.detail;
        } catch (_) {
          /* ignore */
        }
        throw new Error(detail);
      }
      cart.clear();
      renderCartBar();
      drawer.classList.remove("open");
      showToast(cfg.editSession ? "Added to the old bill" : "Order sent — back to tables");
      // Return to Open seats so staff can pick the next table quickly.
      // Historical edit stays on that bill.
      setTimeout(() => {
        if (cfg.editSession) {
          location.href = `/staff/bill/${table}?pin=${encodeURIComponent(pin)}&edited=1&edit_session=${encodeURIComponent(cfg.editSession)}`;
          return;
        }
        location.href = `/staff/tables?pin=${encodeURIComponent(pin)}`;
      }, 450);
    } catch (err) {
      showToast(err.message || "Failed to send order");
      console.error(err);
      btn.disabled = false;
      btn.textContent = "Send order for table";
    }
  });

  renderCartBar();
});
