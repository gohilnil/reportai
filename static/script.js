/**
 * ArogyaAI — Main JavaScript v4.0 (Million Dollar App Theme)
 */

document.addEventListener('DOMContentLoaded', () => {

  /* ── 1. Scroll Reveal Animations (IntersectionObserver) ── */
  const observerOptions = { root: null, rootMargin: '0px', threshold: 0.1 };
  const observer = new IntersectionObserver((entries, observer) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, observerOptions);

  document.querySelectorAll('.animate-in').forEach(el => {
    observer.observe(el);
  });

  /* ── 2. Parallax Background & Cursor Glow ── */
  const bgGrid = document.querySelector('.bg-grid');
  const orb1 = document.querySelector('.bg-orb-1');
  const orb2 = document.querySelector('.bg-orb-2');
  
  // Create cursor glow element if it doesn't exist
  let cursorGlow = document.querySelector('.cursor-glow');
  if (!cursorGlow) {
    cursorGlow = document.createElement('div');
    cursorGlow.className = 'cursor-glow';
    document.body.appendChild(cursorGlow);
  }

  let ticking = false;
  document.addEventListener('mousemove', e => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      const mouseX = e.clientX;
      const mouseY = e.clientY;
      
      const x = (mouseX - cx) / cx;
      const y = (mouseY - cy) / cy;

      // Subtle Background Parallax
      if (bgGrid) bgGrid.style.transform = `translate3d(${x * -20}px, ${y * -20}px, 0)`;
      if (orb1) orb1.style.transform = `translate3d(${x * -40}px, ${y * -40}px, 0)`;
      if (orb2) orb2.style.transform = `translate3d(${x * 30}px, ${y * 30}px, 0)`;

      // Cursor Glow Follow
      cursorGlow.style.left = `${mouseX}px`;
      cursorGlow.style.top = `${mouseY}px`;
      cursorGlow.style.opacity = '1';

      ticking = false;
    });
  });

  // Hide cursor glow when cursor leaves document
  document.addEventListener('mouseout', (e) => {
    if (!e.relatedTarget && e.clientY < 0 || e.clientX < 0 || e.clientX > window.innerWidth || e.clientY > window.innerHeight) {
        cursorGlow.style.opacity = '0';
    }
  });

  /* ── 3. 3D Card Hover Tilt Effect (.card-3d) ── */
  const cards = document.querySelectorAll('.card-3d, .drop-zone');
  cards.forEach(card => {
    card.addEventListener('mousemove', e => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      
      // Calculate rotation (max 8 degrees)
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = ((y - centerY) / centerY) * -8;
      const rotateY = ((x - centerX) / centerX) * 8;
      
      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02)`;
      
      // Update custom properties for inner glow overlay
      card.style.setProperty('--mouse-x', `${x}px`);
      card.style.setProperty('--mouse-y', `${y}px`);
    });
    
    card.addEventListener('mouseleave', () => {
      card.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)`;
    });
  });

  /* ── 4. PDF Drag & Drop Upload ── */
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('pdf_file');
  const dropTitle = document.getElementById('dropTitle');
  const uploadForm = document.getElementById('uploadForm');
  const submitBtn = document.getElementById('submitBtn');
  const submitLbl = document.getElementById('submitLabel');

  if (dropZone && fileInput) {
    const dropLabel = dropZone.querySelector('label');
    if (dropLabel) dropLabel.addEventListener('click', e => e.preventDefault());

    dropZone.addEventListener('click', e => {
      if (e.target.closest('.preview-clear')) return;
      fileInput.click();
    });

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => {
      dropZone.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); });
      document.body.addEventListener(ev, e => e.preventDefault());
    });
    ['dragenter', 'dragover'].forEach(ev => dropZone.addEventListener(ev, () => dropZone.classList.add('dragover')));
    ['dragleave', 'drop'].forEach(ev => dropZone.addEventListener(ev, () => dropZone.classList.remove('dragover')));

    dropZone.addEventListener('drop', e => {
      const file = e.dataTransfer.files[0];
      if (!file) return;
      if (!file.name.toLowerCase().endsWith('.pdf')) {
        showToast('Only PDF files are supported.', 'error');
        return;
      }
      setFileInput(file);
    });

    fileInput.addEventListener('change', function () {
      if (this.files[0]) updateDropUI(this.files[0].name);
    });

    function setFileInput(file) {
      try {
        const dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
      } catch (e) { /* Ignore */ }
      updateDropUI(file.name);
    }

    function updateDropUI(name) {
      if (dropTitle) {
        dropTitle.innerHTML = `
          <span style="color:var(--accent-3); display:flex; align-items:center; gap:6px; justify-content:center;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
            ${name}
          </span>`;
      }
    }
  }

  /* ── 5. Form Submit Loading States ── */
  if (uploadForm) {
    uploadForm.addEventListener('submit', e => {
      if (!fileInput || !fileInput.files || !fileInput.files.length) {
        e.preventDefault();
        showToast('Please select a PDF file first.', 'error');
        return;
      }
      if (submitBtn) {
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        if (submitLbl) submitLbl.textContent = 'AI is explaining your report…';
      }
    });
  }

  /* ── 6. Result Page Tab Switcher with Slider ── */
  const tabs = document.querySelectorAll('.result-tab');
  if (tabs.length > 0) {
    const indicator = document.querySelector('.tab-indicator');
    
    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.result-panel').forEach(p => p.classList.remove('active'));
        
        tab.classList.add('active');
        if (indicator) {
          indicator.style.transform = `translateX(${index * 100}%)`;
        }
        
        const panel = document.getElementById('panel-' + tab.dataset.tab);
        if (panel) panel.classList.add('active');
      });
    });
  }

  /* ── 7. Voice Input Logic (Symptoms Page) ── */
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let isListening = false;

  const micBtn = document.getElementById('micBtn');
  const voiceStatus = document.getElementById('voiceStatus');
  const voiceStatusTx = document.getElementById('voiceStatusText');
  const symptomsInput = document.getElementById('symptomsInput');
  const voiceLang = document.getElementById('voiceLang');
  const charCount = document.getElementById('charCount');
  const notSupported = document.getElementById('voiceNotSupported');

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
    recognition = new SpeechRecognition();
    recognition.lang = voiceLang ? voiceLang.value : 'en-IN';
    recognition.continuous = true;
    recognition.interimResults = true;
    let finalTranscript = symptomsInput ? symptomsInput.value : '';

    recognition.onstart = () => {
      isListening = true;
      if (micBtn) { micBtn.classList.add('listening'); micBtn.textContent = '⏹'; }
      if (symptomsInput) symptomsInput.classList.add('listening');
      if (voiceStatus) voiceStatus.classList.add('active');
      if (voiceStatusTx) voiceStatusTx.textContent = 'Listening… speak now';
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
    if (micBtn) { micBtn.classList.remove('listening'); micBtn.textContent = '🎤'; }
    if (symptomsInput) { 
        symptomsInput.classList.remove('listening'); 
        symptomsInput.value = symptomsInput.value.trim(); 
        if (charCount) charCount.textContent = symptomsInput.value.length; 
    }
    if (voiceStatus) voiceStatus.classList.remove('active');
  }

  /* ── 8. Symptoms Form Submit ── */
  const symptomForm = document.getElementById('symptomForm');
  const symptomBtn = document.getElementById('symptomBtn');
  const symptomLbl = document.getElementById('symptomBtnLabel');
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
        symptomBtn.classList.add('loading');
        symptomBtn.disabled = true;
        if (symptomLbl) symptomLbl.textContent = '⏳ Analyzing…';
      }
    });
  }

  /* ── 9. Toast Notification System ── */
  window.showToast = function(msg, type = 'info') {
    document.querySelector('.toast')?.remove();
    const toast = document.createElement('div');
    toast.className = 'toast';
    const isError = type === 'error';
    const icon = isError ? '⚠️' : '✅';
    
    toast.style.cssText = `
      position: fixed; bottom: 32px; right: 32px; z-index: 9999;
      padding: 14px 20px; border-radius: var(--radius-md); font-size: 0.9rem; font-weight: 600;
      display: flex; align-items: center; gap: 12px; animation: slideInRight 0.5s var(--spring) forwards;
      backdrop-filter: var(--glass-blur-2); max-width: 400px;
      box-shadow: var(--shadow-lg), inset 0 1px 1px rgba(255,255,255,0.1); font-family: var(--font-body);
      ${isError ? 'background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); color: #fca5a5;' 
                : 'background: rgba(16,185,129,0.1); border: 1px solid rgba(16,185,129,0.3); color: #6ee7b7;'}
    `;
    
    toast.innerHTML = `<span style="font-size:1.2rem">${icon}</span> <span>${msg}</span>`;
    document.body.appendChild(toast);
    
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(40px) scale(0.95)';
      toast.style.transition = 'all 0.4s var(--ease-out)';
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  };

  /* ── 10. Initial Animations Confidence Bar ── */
  setTimeout(() => {
    const confBar = document.querySelector('.conf-bar');
    if (confBar) {
      const width = confBar.style.width;
      confBar.style.width = '0%';
      setTimeout(() => confBar.style.width = width, 100);
    }
  }, 100);

});