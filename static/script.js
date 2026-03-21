/**
 * ArogyaAI — Main JavaScript v3.0
 * Fixes: double file picker, responsive nav, voice, tabs, toasts
 */

document.addEventListener('DOMContentLoaded', () => {

  /* ── Entrance animations ─────────────────────── */
  document.querySelectorAll('.animate-in').forEach((el, i) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(14px)';
    setTimeout(() => {
      el.style.transition = 'opacity 0.5s cubic-bezier(0.16,1,0.3,1), transform 0.5s cubic-bezier(0.16,1,0.3,1)';
      el.style.opacity = '1';
      el.style.transform = 'translateY(0)';
    }, 60 + i * 80);
  });

  /* ─────────────────────────────────────────────────
     PDF UPLOAD — FIX: prevent double file picker
     The bug was: dropZone click → triggers label click
     → label click → triggers input click = opens TWICE
  ───────────────────────────────────────────────── */
  const dropZone   = document.getElementById('dropZone');
  const fileInput  = document.getElementById('pdf_file');
  const dropTitle  = document.getElementById('dropTitle');
  const uploadForm = document.getElementById('uploadForm');
  const submitBtn  = document.getElementById('submitBtn');
  const submitLbl  = document.getElementById('submitLabel');

  if (dropZone && fileInput) {

    // CRITICAL FIX: Remove the label's default click behaviour
    // so only our controlled click fires — not label + input both
    const dropLabel = dropZone.querySelector('label');
    if (dropLabel) {
      dropLabel.addEventListener('click', e => e.preventDefault());
    }

    // Single controlled click on the zone opens picker once
    dropZone.addEventListener('click', e => {
      // Don't trigger if clicking the clear/remove button
      if (e.target.closest('.preview-clear')) return;
      fileInput.click();
    });

    // Drag events — prevent browser default (open file)
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => {
      dropZone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); });
      document.body.addEventListener(ev, e => e.preventDefault());
    });
    ['dragenter', 'dragover'].forEach(ev =>
      dropZone.addEventListener(ev, () => dropZone.classList.add('dragover'))
    );
    ['dragleave', 'drop'].forEach(ev =>
      dropZone.addEventListener(ev, () => dropZone.classList.remove('dragover'))
    );

    // Handle dropped file
    dropZone.addEventListener('drop', e => {
      const file = e.dataTransfer.files[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Only PDF files are supported.', 'error');
        return;
      }
      setFileInput(file);
    });

    // Handle picked file
    fileInput.addEventListener('change', function () {
      if (this.files[0]) updateDropUI(this.files[0].name);
    });

    function setFileInput(file) {
      try {
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
      } catch (e) {
        // DataTransfer not supported in some browsers — file already in input
      }
      updateDropUI(file.name);
    }

    function updateDropUI(name) {
      if (dropTitle) {
        dropTitle.innerHTML = `
          <span style="color:#6ee7b7; display:flex; align-items:center; gap:6px; justify-content:center;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            ${name}
          </span>`;
      }
    }
  }

  // Submit loading state
  if (uploadForm) {
    uploadForm.addEventListener('submit', e => {
      if (!fileInput || !fileInput.files || !fileInput.files.length) {
        e.preventDefault();
        showToast('Please select a PDF file first.', 'error');
        return;
      }
      if (submitBtn) {
        submitBtn.disabled = true;
        if (submitLbl) submitLbl.textContent = 'AI is reading your report…';
      }
    });
  }

  /* ── Result page tabs ─────────────────────────── */
  document.querySelectorAll('.result-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.result-tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.result-panel').forEach(p => p.classList.remove('active'));
      tab.classList.add('active');
      const panel = document.getElementById('panel-' + tab.dataset.tab);
      if (panel) panel.classList.add('active');
    });
  });

  /* ── Voice input ──────────────────────────────── */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition   = null;
  let isListening   = false;

  const micBtn        = document.getElementById('micBtn');
  const voiceStatus   = document.getElementById('voiceStatus');
  const voiceStatusTx = document.getElementById('voiceStatusText');
  const symptomsInput = document.getElementById('symptomsInput');
  const voiceLang     = document.getElementById('voiceLang');
  const charCount     = document.getElementById('charCount');
  const notSupported  = document.getElementById('voiceNotSupported');

  if (micBtn) {
    if (!SpeechRecognition) {
      if (notSupported) notSupported.style.display = 'block';
      micBtn.style.opacity = '0.4';
      micBtn.style.cursor  = 'not-allowed';
      micBtn.title = 'Voice not supported. Use Chrome or Edge.';
    }
    micBtn.addEventListener('click', () => {
      if (!SpeechRecognition) return;
      isListening ? stopListening() : startListening();
    });
  }

  if (symptomsInput && charCount) {
    symptomsInput.addEventListener('input', () => {
      charCount.textContent = symptomsInput.value.length;
    });
  }

  function startListening() {
    recognition      = new SpeechRecognition();
    recognition.lang = voiceLang ? voiceLang.value : 'en-IN';
    recognition.continuous     = true;
    recognition.interimResults = true;
    let finalTranscript = symptomsInput ? symptomsInput.value : '';

    recognition.onstart = () => {
      isListening = true;
      if (micBtn)       { micBtn.classList.add('listening'); micBtn.textContent = '⏹'; }
      if (symptomsInput)  symptomsInput.classList.add('listening');
      if (voiceStatus)    voiceStatus.classList.add('active');
      if (voiceStatusTx)  voiceStatusTx.textContent = 'Listening… speak now';
    };
    recognition.onresult = e => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalTranscript += t + ' ';
        else interim = t;
      }
      if (symptomsInput) {
        symptomsInput.value = finalTranscript + interim;
        if (charCount) charCount.textContent = symptomsInput.value.length;
      }
      if (voiceStatusTx) voiceStatusTx.textContent = interim ? `Hearing: "${interim.substring(0,40)}…"` : 'Listening…';
    };
    recognition.onerror = e => {
      const msgs = { 'not-allowed': '❌ Mic denied.', 'no-speech': '🔇 No speech detected.', 'network': '🌐 Network error.' };
      if (voiceStatusTx) voiceStatusTx.textContent = msgs[e.error] || 'Error. Try again.';
      setTimeout(stopListening, 2000);
    };
    recognition.onend = () => { if (isListening) stopListening(); };
    recognition.start();
  }

  function stopListening() {
    if (recognition) { recognition.stop(); recognition = null; }
    isListening = false;
    if (micBtn)       { micBtn.classList.remove('listening'); micBtn.textContent = '🎤'; }
    if (symptomsInput) { symptomsInput.classList.remove('listening'); symptomsInput.value = symptomsInput.value.trim(); if (charCount) charCount.textContent = symptomsInput.value.length; }
    if (voiceStatus)   voiceStatus.classList.remove('active');
  }

  /* ── Symptom form submit ──────────────────────── */
  const symptomForm = document.getElementById('symptomForm');
  const symptomBtn  = document.getElementById('symptomBtn');
  const symptomLbl  = document.getElementById('symptomBtnLabel');
  if (symptomForm) {
    symptomForm.addEventListener('submit', e => {
      const val = symptomsInput ? symptomsInput.value.trim() : '';
      if (val.length < 10) {
        e.preventDefault();
        showToast('Please describe your symptoms in more detail.', 'error');
        if (symptomsInput) symptomsInput.focus();
        return;
      }
      if (isListening) stopListening();
      if (symptomBtn) {
        symptomBtn.disabled = true;
        if (symptomLbl) symptomLbl.textContent = '⏳ Analyzing…';
      }
    });
  }

  /* ── Navbar scroll effect ─────────────────────── */
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      navbar.style.background = window.scrollY > 10 ? 'rgba(3,7,18,0.97)' : 'rgba(3,7,18,0.85)';
    }, { passive: true });
  }

  /* ── Subtle bg parallax ───────────────────────── */
  const bgScene = document.querySelector('.bg-scene');
  if (bgScene && window.innerWidth > 768) {
    let ticking = false;
    document.addEventListener('mousemove', e => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        const x = (e.clientX / window.innerWidth  - 0.5) * 20;
        const y = (e.clientY / window.innerHeight - 0.5) * 14;
        bgScene.style.transform = `translate(${x * 0.12}px, ${y * 0.08}px)`;
        ticking = false;
      });
    });
  }

  /* ── Toast ────────────────────────────────────── */
  window.showToast = function(msg, type = 'info') {
    document.querySelector('.toast')?.remove();
    const toast = document.createElement('div');
    toast.className = 'toast';
    const isError = type === 'error';
    toast.style.cssText = `
      position:fixed; bottom:24px; right:24px; z-index:9999;
      padding:11px 16px; border-radius:var(--radius-sm);
      font-size:0.85rem; font-weight:500;
      display:flex; align-items:center; gap:8px;
      animation:fadeUp 0.3s ease both;
      backdrop-filter:blur(12px); max-width:320px;
      font-family:var(--font-body);
      ${isError
        ? 'background:rgba(239,68,68,0.12);border:1px solid rgba(239,68,68,0.3);color:#fca5a5;'
        : 'background:rgba(16,185,129,0.12);border:1px solid rgba(16,185,129,0.3);color:#6ee7b7;'}
    `;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(8px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  };

});