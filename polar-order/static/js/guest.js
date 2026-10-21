document.addEventListener("DOMContentLoaded", () => {
  const table = window.POLAR_TABLE;
  const cart = new Map(); // itemId -> {id,name,price,qty,note}

  const cartBar = document.getElementById("cartBar");
  const cartCount = document.getElementById("cartCount");
  const cartTotal = document.getElementById("cartTotal");
  const drawer = document.getElementById("drawer");
  const cartLines = document.getElementById("cartLines");
  const toast = document.getElementById("toast");
  if (!cartBar || !drawer) return;

  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2200);
  }

  function money(n) {
    return `$${Math.round(n)}`;
  }

  function renderCartBar() {
    let qty = 0;
    let total = 0;
    for (const line of cart.values()) {
      qty += line.qty;
      total += line.qty * line.price;
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
    if (!cart.size) {
      cartLines.innerHTML = `<p class="muted">Cart is empty.</p>`;
      return;
    }
    for (const line of cart.values()) {
      const row = document.createElement("div");
      row.className = "cart-line";
      row.innerHTML = `
        <div>
          <strong>${line.name}</strong>
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
        <div>${money(line.qty * line.price)}</div>
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
      const id = card.dataset.id;
      const existing = cart.get(id);
      if (existing) existing.qty += 1;
      else {
        cart.set(id, {
          id,
          name: card.dataset.name,
          price: Number(card.dataset.price),
          qty: 1,
          note: "",
          allowNote: card.dataset.allowNote === "1",
        });
      }
      renderCartBar();
      showToast("Added");
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
    const partySize = Number(document.getElementById("partySize").value || 1);
    const payload = {
      party_size: partySize,
      note: document.getElementById("orderNote").value || null,
      items: [...cart.values()].map((l) => ({
        item_id: l.id,
        qty: l.qty,
        note: l.note || null,
      })),
    };
    const btn = document.getElementById("submitOrder");
    btn.disabled = true;
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
      showToast("Order sent");
    } catch (err) {
      showToast("Failed to send order");
      console.error(err);
    } finally {
      btn.disabled = false;
      btn.textContent = "Send to bar";
    }
  });
});
