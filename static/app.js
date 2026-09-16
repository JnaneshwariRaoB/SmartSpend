// ── Theme ──────────────────────────────────────────────────────────────────
function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", next);
  document.getElementById("theme-icon").textContent = next === "dark" ? "☀️" : "🌙";
}

// ── Helpers ────────────────────────────────────────────────────────────────
function fmt(amount, currency) {
  return `${currency} ${Number(amount).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function show(id)  { document.getElementById(id).classList.remove("hidden"); }
function hide(id)  { document.getElementById(id).classList.add("hidden"); }

// ── Load profile (both sidebars) ───────────────────────────────────────────
async function loadProfile() {
  // Reset
  hide("bank-content");    show("bank-loading");
  hide("profile-content"); show("profile-loading");

  try {
    const res  = await fetch("/api/profile");
    const data = await res.json();

    if (!data.ok) throw new Error(data.error);

    const cur = data.raw.currency;

    // ── Left sidebar: bank data ──────────────────────────────────────────
    document.getElementById("bal-value").textContent = fmt(data.raw.balance, cur);
    document.getElementById("tx-count").textContent  = `${data.raw.tx_count} entries`;

    const txList = document.getElementById("tx-list");
    txList.innerHTML = "";
    data.raw.transactions.forEach(t => {
      const isIn    = t.amount < 0;
      const abs     = Math.abs(t.amount);
      const row     = document.createElement("div");
      row.className = "tx-row";
      row.innerHTML = `
        <span class="tx-badge ${isIn ? "in" : "out"}">${isIn ? "IN" : "OUT"}</span>
        <span class="tx-merchant">${t.merchant || t.description}</span>
        <span class="tx-date">${t.date}</span>
        <span class="tx-amount ${isIn ? "in" : "out"}">${isIn ? "+" : "-"}${cur} ${abs.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2})}</span>
      `;
      txList.appendChild(row);
    });

    hide("bank-loading"); show("bank-content");

    // ── Right sidebar: profile ───────────────────────────────────────────
    const p = data.profile;

    document.getElementById("prof-buffer").textContent = fmt(p.minimum_balance, cur);

    // Income
    const incEl = document.getElementById("prof-income");
    incEl.innerHTML = "";
    if (p.income.length === 0) {
      incEl.innerHTML = `<div class="profile-row"><span class="prof-name" style="color:var(--text-muted)">None detected</span></div>`;
    } else {
      p.income.forEach(i => {
        const row = document.createElement("div");
        row.className = "profile-row";
        row.innerHTML = `
          <div>
            <div class="prof-name">${i.source}</div>
            <div class="prof-meta">${i.frequency} · next ${i.next_date}</div>
          </div>
          <span class="prof-amt income">+${fmt(i.amount, cur)}</span>
        `;
        incEl.appendChild(row);
      });
    }

    // Essential expenses
    const essEl = document.getElementById("prof-essential");
    essEl.innerHTML = "";
    if (p.essential.length === 0) {
      essEl.innerHTML = `<div class="profile-row"><span class="prof-name" style="color:var(--text-muted)">None detected</span></div>`;
    } else {
      p.essential.forEach(e => {
        const row = document.createElement("div");
        row.className = "profile-row";
        row.innerHTML = `
          <div>
            <div class="prof-name">${e.merchant}</div>
            <div class="prof-meta">${e.frequency} · next ${e.next_due}</div>
          </div>
          <span class="prof-amt essential">-${fmt(e.amount, cur)}</span>
        `;
        essEl.appendChild(row);
      });
    }

    // Flexible expenses
    const flexEl = document.getElementById("prof-flexible");
    flexEl.innerHTML = "";
    if (p.flexible.length === 0) {
      flexEl.innerHTML = `<div class="profile-row"><span class="prof-name" style="color:var(--text-muted)">None detected</span></div>`;
    } else {
      p.flexible.forEach(e => {
        const row = document.createElement("div");
        row.className = "profile-row";
        row.innerHTML = `
          <div>
            <div class="prof-name">${e.merchant}</div>
            <div class="prof-meta">${e.frequency} · next ${e.next_due}</div>
          </div>
          <span class="prof-amt flexible">-${fmt(e.amount, cur)}</span>
        `;
        flexEl.appendChild(row);
      });
    }

    // Monthly summary
    document.getElementById("sum-income").textContent    = fmt(p.monthly_income, cur);
    document.getElementById("sum-essential").textContent = fmt(p.monthly_essential, cur);
    document.getElementById("sum-flexible").textContent  = fmt(p.monthly_flexible, cur);
    document.getElementById("sum-surplus").textContent   = fmt(p.monthly_surplus, cur);

    hide("profile-loading"); show("profile-content");

  } catch (err) {
    console.error(err);
    document.getElementById("bank-loading").innerHTML  = `<p style="color:var(--red)">Error: ${err.message}</p>`;
    document.getElementById("profile-loading").innerHTML = `<p style="color:var(--red)">Error: ${err.message}</p>`;
  }
}

// ── Analyse ────────────────────────────────────────────────────────────────
async function analyse() {
  const text     = document.getElementById("req-text").value.trim();
  const amount   = parseFloat(document.getElementById("req-amount").value);
  const deadline = document.getElementById("req-deadline").value;
  const type     = document.getElementById("req-type").value;
  const partial  = document.getElementById("req-partial").checked;

  if (!text || !amount || !deadline) {
    alert("Please fill in all fields.");
    return;
  }

  // Loading state
  const btn = document.querySelector(".analyse-btn");
  btn.disabled = true;
  document.getElementById("btn-label").classList.add("hidden");
  document.getElementById("btn-spinner").classList.remove("hidden");
  hide("result-card");

  try {
    const res  = await fetch("/api/analyse", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({
        request_text:    text,
        amount:          amount,
        deadline:        deadline,
        request_type:    type,
        allows_partial:  partial,
      }),
    });
    const data = await res.json();

    if (!data.ok) throw new Error(data.error);

    const cur = data.currency;

    // Status badge
    const statusBadge = document.getElementById("result-status-badge");
    statusBadge.textContent = data.affordability_status.replace(/_/g, " ").toUpperCase();
    statusBadge.className   = `status-badge badge-${data.affordability_status}`;

    // Method badge
    const methodBadge = document.getElementById("result-method-badge");
    methodBadge.textContent = data.recommended_payment_method.replace(/_/g, " ").toUpperCase();
    methodBadge.className   = "method-badge";

    // Safe amount & earliest date
    document.getElementById("res-safe").textContent     = fmt(data.amount_safe_to_pay, cur);
    document.getElementById("res-earliest").textContent = data.earliest_date;

    // Payment plan
    const planBlock = document.getElementById("res-plan-block");
    const planEl    = document.getElementById("res-plan");
    planEl.innerHTML = "";
    if (data.payment_plan && data.payment_plan.length > 0) {
      show("res-plan-block");
      data.payment_plan.forEach(p => {
        const row = document.createElement("div");
        row.className = "plan-row";
        row.innerHTML = `<span class="plan-date">${p.date}</span><span class="plan-amt">${fmt(p.amount, cur)}</span>`;
        planEl.appendChild(row);
      });
    } else {
      hide("res-plan-block");
    }

    // Spending cuts
    const cutsBlock = document.getElementById("res-cuts-block");
    const cutsEl    = document.getElementById("res-cuts");
    cutsEl.innerHTML = "";
    if (data.spending_changes_needed && data.spending_changes_needed.length > 0) {
      show("res-cuts-block");
      data.spending_changes_needed.forEach(c => {
        const row = document.createElement("div");
        row.className = "cut-row";
        row.innerHTML = `
          <span class="cut-cat">${c.category}</span>
          <span class="cut-action cut-${c.action}">${c.action.toUpperCase()}</span>
        `;
        cutsEl.appendChild(row);
      });
    } else {
      hide("res-cuts-block");
    }

    // Explanation
    document.getElementById("res-explanation").textContent = data.explanation;

    show("result-card");

  } catch (err) {
    console.error(err);
    alert("Analysis failed: " + err.message);
  } finally {
    btn.disabled = false;
    document.getElementById("btn-label").classList.remove("hidden");
    document.getElementById("btn-spinner").classList.add("hidden");
  }
}

// ── Set default deadline to 30 days from today ─────────────────────────────
(function init() {
  const d = new Date();
  d.setDate(d.getDate() + 30);
  document.getElementById("req-deadline").value = d.toISOString().split("T")[0];
  loadProfile();
})();
