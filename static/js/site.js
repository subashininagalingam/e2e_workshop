(function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ---- Register page: workshop summary, hybrid mode, then payment step ---- */
  const metaEl = document.getElementById('workshop-meta');
  if (metaEl) {
    const meta = JSON.parse(metaEl.textContent);
    const form = document.getElementById('reg-form');
    const sel = document.getElementById('id_workshop');
    const sum = document.getElementById('summary');
    const modeBox = document.getElementById('mode-box');
    const step2 = document.getElementById('step2');
    const steps = document.getElementById('steps');
    const nextBtn = document.getElementById('next');
    const submitBtn = document.getElementById('submit');
    const proof = document.getElementById('id_payment_screenshot');
    const preview = document.getElementById('proof-preview');
    let unlocked = form.dataset.hasErrors === '1';   // after a server error, show everything again

    const certBox = document.getElementById('cert-box');
    const certRadios = form.querySelectorAll('input[name="wants_certificate"]');
    const wantsYes = () => { const c = form.querySelector('input[name="wants_certificate"]:checked'); return !!c && c.value === 'yes'; };
    const payNeeded = (m) => !!m && m.pay && (!m.choice || wantsYes());

    const render = () => {
      const m = meta[sel.value];
      if (!m) {
        sum.innerHTML = Object.keys(meta).length > 1 ? '<div class="alert alert-info mb-0"><i class="bi bi-info-circle me-1"></i>Several workshops are open. Please choose the one you want to attend.</div>' : '';
        modeBox.hidden = true; certBox.hidden = true; step2.hidden = true; steps.hidden = true; nextBtn.hidden = true; submitBtn.hidden = false; proof.required = false;
        return;
      }
      const poster = m.poster ? `<div style="width:96px;flex:none"><img class="thumb-poster" src="${esc(m.poster)}" alt=""></div>` : '';
      const seats = m.seats ? `<span class="seats${m.seats_low ? ' seats-low' : ''}"><i class="dot" aria-hidden="true"></i>${esc(m.seats)}</span>` : '';
      sum.innerHTML = `<article class="card-e2e p-3"><div class="d-flex gap-3 align-items-center">${poster}<div>
        <h2 class="h6 fw-bold mb-1">${esc(m.title)}</h2>
        <div class="meta-row"><span><i class="bi bi-calendar-event"></i>${esc(m.date)}</span><span><i class="bi bi-clock"></i>${esc(m.time)}</span><span class="text-capitalize"><i class="bi bi-diagram-2"></i>${esc(m.mode)}</span>${m.venue ? `<span><i class="bi bi-geo-alt"></i>${esc(m.venue)}</span>` : ''}${seats}</div></div></div></article>`;
      modeBox.hidden = !m.hybrid;
      certBox.hidden = !(m.pay && m.choice);
      certRadios.forEach((r) => { r.required = !!(m.pay && m.choice); });
      document.getElementById('cert-fee').textContent = m.fee || '';
      const need = payNeeded(m);
      steps.hidden = !need;
      proof.required = need;
      if (need) {
        document.getElementById('pay-fee').textContent = m.fee;
        const qr = document.getElementById('pay-qr');
        qr.hidden = !m.payqr; if (m.payqr) qr.src = m.payqr;
        document.getElementById('pay-upi-line').hidden = !m.upi;
        document.getElementById('pay-upi').textContent = m.upi;
      }
      step2.hidden = !(need && unlocked);
      nextBtn.hidden = !(need && !unlocked);
      submitBtn.hidden = need && !unlocked;
      document.getElementById('st1').classList.toggle('on', !(need && unlocked));
      document.getElementById('st2').classList.toggle('on', !!(need && unlocked));
    };
    certRadios.forEach((r) => r.addEventListener('change', () => { unlocked = false; render(); }));

    nextBtn.addEventListener('click', () => {
      const fields = document.querySelectorAll('#step1 input, #step1 select, #step1 textarea');
      for (const el of fields) {
        if (el.offsetParent !== null && !el.checkValidity()) { el.reportValidity(); return; }
      }
      unlocked = true; render();
      step2.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    proof.addEventListener('change', () => {
      const f = proof.files && proof.files[0];
      if (f) { preview.src = URL.createObjectURL(f); preview.hidden = false; } else { preview.hidden = true; }
    });
    sel.addEventListener('change', render);
    render();

    form.addEventListener('submit', () => { submitBtn.disabled = true; submitBtn.textContent = 'Submitting…'; });
    window.addEventListener('pageshow', () => { submitBtn.disabled = false; submitBtn.textContent = 'Submit Registration'; });
  }

  /* ---- Countdown to the registration deadline: days, hours, minutes, seconds ---- */
  document.querySelectorAll('.countdown[data-deadline]').forEach((el) => {
    const end = new Date(el.dataset.deadline).getTime();
    if (!isFinite(end)) { el.hidden = true; return; }
    const label = el.querySelector('.cd-label');
    const set = (k, v) => { const n = el.querySelector('[data-' + k + ']'); if (n) n.textContent = String(v).padStart(2, '0'); };
    let timer;
    const tick = () => {
      const left = Math.floor((end - Date.now()) / 1000);
      if (left <= 0) {
        clearInterval(timer);
        el.classList.add('done'); el.classList.remove('urgent');
        label.textContent = 'Registration has closed';
        ['d', 'h', 'm', 's'].forEach((k) => set(k, 0));
        return;
      }
      set('d', Math.floor(left / 86400)); set('h', Math.floor(left % 86400 / 3600));
      set('m', Math.floor(left % 3600 / 60)); set('s', left % 60);
      const urgent = left < 86400;
      el.classList.toggle('urgent', urgent);
      label.textContent = urgent ? 'Last day! Registration closes in' : 'Registration closes in';
    };
    tick(); timer = setInterval(tick, 1000);
  });

  /* ---- Registration: hide demo-class details when the answer is "No" ---- */
  const demoSel = document.getElementById('id_demo_interest');
  if (demoSel) {
    const toggleDemo = () => document.querySelectorAll('[data-demo]').forEach((el) => { el.hidden = demoSel.value === 'No'; });
    demoSel.addEventListener('change', toggleDemo); toggleDemo();
  }

  /* ---- Staff: tick boxes that save by themselves, and confirm-before-click buttons ---- */
  document.querySelectorAll('[data-autosubmit]').forEach((box) => box.addEventListener('change', () => { box.disabled = true; box.form.submit(); }));
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-confirm-click]');
    if (b && !confirm(b.dataset.confirmClick)) e.preventDefault();
  });

  /* ---- Certificate setup: live preview while the numbers change ---- */
  const certForm = document.getElementById('cert-form');
  const certImg = document.getElementById('cert-preview');
  if (certForm && certImg) {
    let timer;
    const refresh = () => {
      const q = new URLSearchParams({
        name: document.getElementById('sample-name').value || 'Sample Student Name',
        x: document.getElementById('id_cert_name_x').value, y: document.getElementById('id_cert_name_y').value,
        size: document.getElementById('id_cert_font_size').value, color: document.getElementById('id_cert_color').value,
        font: document.getElementById('id_cert_font').value, idtext: document.getElementById('id_cert_id_start').value,
        idx: document.getElementById('id_cert_id_x').value, idy: document.getElementById('id_cert_id_y').value, idsize: document.getElementById('id_cert_id_size').value, t: Date.now(),
      });
      certImg.src = certForm.dataset.preview + '?' + q.toString();
    };
    certForm.querySelectorAll('input:not([type=file]), select').forEach((el) => el.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(refresh, 250); }));
  }

  /* ---- Image lightbox (previous workshops) ---- */
  const lb = document.getElementById('lightbox');
  if (lb && window.bootstrap) {
    const modal = new bootstrap.Modal(lb);
    document.addEventListener('click', (e) => {
      const fig = e.target.closest('[data-lightbox]');
      if (!fig) return;
      lb.querySelector('img').src = fig.dataset.src;
      lb.querySelector('img').alt = fig.dataset.cap || '';
      document.getElementById('lightbox-cap').textContent = fig.dataset.cap || '';
      modal.show();
    });
  }

  /* ---- Confirm before deleting ---- */
  document.querySelectorAll('form[data-confirm]').forEach((f) => f.addEventListener('submit', (e) => {
    if (!confirm(f.dataset.confirm)) e.preventDefault();
  }));

  /* ---- Thank-you page: redirect to the official website ---- */
  const line = document.getElementById('count-line');
  if (line) {
    const url = line.dataset.url;
    let left = parseInt(line.dataset.seconds, 10) || 12;
    const tick = () => { line.textContent = `Taking you to the Errors2Experts website in ${left}s…`; if (left-- <= 0) { clearInterval(t); location.href = url; } };
    const t = setInterval(tick, 1000); tick();
    document.getElementById('stay').addEventListener('click', () => { clearInterval(t); line.textContent = 'Auto-redirect cancelled.'; });
  }

  /* ---- Share button ---- */
  document.querySelectorAll('[data-share]').forEach((b) => b.addEventListener('click', () => {
    const data = { title: b.dataset.title, url: location.href };
    if (navigator.share) navigator.share(data).catch(() => {});
    else navigator.clipboard.writeText(location.href).then(() => alert('Link copied to clipboard.'), () => prompt('Copy this link:', location.href));
  }));

  /* ---- Dashboard chart ---- */
  const td = document.getElementById('trend-data');
  if (td && window.Chart) {
    const d = JSON.parse(td.textContent);
    new Chart(document.getElementById('trend'), { type: 'bar', data: { labels: d.labels, datasets: [{ label: 'Registrations', data: d.values, backgroundColor: '#1b8a3f' }] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } } });
  }

  /* ---- Print ---- */
  document.querySelectorAll('[data-print]').forEach((b) => b.addEventListener('click', () => window.print()));
})();
