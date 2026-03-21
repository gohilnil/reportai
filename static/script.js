/* script.js */

document.addEventListener("DOMContentLoaded", () => {
  // 1. Setup Three.js 3D Background Scene (only if canvas-container exists)
  const container = document.getElementById('canvas-container');
  if (container && typeof THREE !== 'undefined') {
    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x020408, 0.0015);

    const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.z = 40;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Floating 3D Geometric Shapes
    const shapes = [];
    const geometries = [
      new THREE.IcosahedronGeometry(2, 0),
      new THREE.TorusGeometry(1.5, 0.5, 16, 100),
      new THREE.OctahedronGeometry(2, 0)
    ];
    // colors: indigo and violet
    const colors = [0x6366f1, 0x8b5cf6];

    for (let i = 0; i < 20; i++) {
      const geo = geometries[Math.floor(Math.random() * geometries.length)];
      const col = colors[Math.floor(Math.random() * colors.length)];
      // Wireframe materials for high-tech premium feel
      const mat = new THREE.MeshBasicMaterial({ 
        color: col, 
        wireframe: true, 
        transparent: true, 
        opacity: 0.15 + Math.random() * 0.15 
      });
      const mesh = new THREE.Mesh(geo, mat);
      
      mesh.position.x = (Math.random() - 0.5) * 100;
      mesh.position.y = (Math.random() - 0.5) * 80;
      mesh.position.z = (Math.random() - 0.5) * 60 - 20;
      
      mesh.rotation.x = Math.random() * Math.PI;
      mesh.rotation.y = Math.random() * Math.PI;

      // Random rotation speeds
      mesh.userData = {
        rx: (Math.random() - 0.5) * 0.01,
        ry: (Math.random() - 0.5) * 0.01
      };

      scene.add(mesh);
      shapes.push(mesh);
    }

    // Particles Field
    const particlesGeo = new THREE.BufferGeometry();
    const particleCount = 2000;
    const posArray = new Float32Array(particleCount * 3);
    for(let i=0; i < particleCount * 3; i++) {
      posArray[i] = (Math.random() - 0.5) * 150;
    }
    particlesGeo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
    const particlesMat = new THREE.PointsMaterial({
      size: 0.15,
      color: 0x6366f1,
      transparent: true,
      opacity: 0.4
    });
    const particlesMesh = new THREE.Points(particlesGeo, particlesMat);
    scene.add(particlesMesh);

    // Mouse Parallax
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;
    const windowHalfX = window.innerWidth / 2;
    const windowHalfY = window.innerHeight / 2;

    document.addEventListener('mousemove', (event) => {
      mouseX = (event.clientX - windowHalfX);
      mouseY = (event.clientY - windowHalfY);
    });

    window.addEventListener('resize', () => {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });

    const animate = function () {
      requestAnimationFrame(animate);

      targetX = mouseX * 0.001;
      targetY = mouseY * 0.001;

      shapes.forEach(mesh => {
        mesh.rotation.x += mesh.userData.rx;
        mesh.rotation.y += mesh.userData.ry;
      });

      particlesMesh.rotation.y += 0.0005;
      
      // extremely subtle camera rotation based on mouse
      camera.position.x += (mouseX * 0.01 - camera.position.x) * 0.05;
      camera.position.y += (-mouseY * 0.01 - camera.position.y) * 0.05;
      camera.lookAt(scene.position);

      renderer.render(scene, camera);
    };
    animate();
  }

  // 2. Drag & Drop Upload Handlers
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('pdf_file');
  const dropTitle = document.getElementById('dropTitle');

  if (dropZone && fileInput) {
    dropZone.addEventListener('click', () => fileInput.click());

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, preventDefaults, false);
      document.body.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }

    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => dropZone.classList.add('dragover'), false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, () => dropZone.classList.remove('dragover'), false);
    });

    dropZone.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files.length) {
        if (!files[0].name.toLowerCase().endsWith('.pdf')) {
          showToast('Please upload a PDF file', 'error');
          return;
        }
        fileInput.files = files;
        updateFileName(files[0].name);
      }
    }

    fileInput.addEventListener('change', function() {
      if (this.files && this.files[0]) {
        updateFileName(this.files[0].name);
      }
    });

    function updateFileName(name) {
      if (dropTitle) {
        dropTitle.innerHTML = `<span style="color: var(--accent3);">${name}</span>`;
      }
    }
  }

  // 4. Form Submit Handler
  const uploadForm = document.getElementById('uploadForm');
  const submitBtn = document.getElementById('submitBtn');
  const submitLabel = document.getElementById('submitLabel');

  if (uploadForm && submitBtn) {
    uploadForm.addEventListener('submit', (e) => {
      if (!fileInput || !fileInput.files.length) {
        e.preventDefault();
        showToast('Please select a PDF file before explaining', 'error');
        return;
      }
      submitBtn.classList.add('loading');
      if (submitLabel) submitLabel.textContent = 'Analyzing Report...';
    });
  }

  // 5. Tab Switching (Result Page)
  const tabs = document.querySelectorAll('.result-tab');
  if (tabs.length > 0) {
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        // Remove active from all
        document.querySelectorAll('.result-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.result-panel').forEach(p => p.classList.remove('active'));
        
        // Add active to clicked
        tab.classList.add('active');
        const targetId = `panel-${tab.dataset.tab}`;
        const targetPanel = document.getElementById(targetId);
        if (targetPanel) {
          targetPanel.classList.add('active');
          // GSAP internal content subtle animation for 3D feel
          if (typeof gsap !== 'undefined') {
            gsap.fromTo(targetPanel.querySelector('.result-content'),
              { y: 15, opacity: 0, scale: 0.98 },
              { y: 0, opacity: 1, scale: 1, duration: 0.4, ease: "power2.out" }
            );
          }
        }
      });
    });
  }

  // 6. Toast Function
  window.showToast = function(message, type = 'info') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 16px 24px;
      background: rgba(8, 12, 20, 0.9);
      border: 1px solid ${type === 'error' ? 'rgba(239,68,68,0.3)' : 'rgba(99,102,241,0.3)'};
      border-radius: 12px;
      color: ${type === 'error' ? '#fca5a5' : '#fff'};
      font-size: 0.95rem;
      backdrop-filter: blur(10px);
      box-shadow: 0 10px 40px rgba(0,0,0,0.5);
      z-index: 9999;
      animation: slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) both;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 3000);
  };

  // Optional GSAP Page Internals (NOT on body/page wrappers to avoid invisible bug)
  if (typeof gsap !== 'undefined') {
    const featureCards = document.querySelectorAll('.feature-card');
    if (featureCards.length > 0) {
      gsap.fromTo(featureCards, 
        { y: 40, opacity: 0 },
        { y: 0, opacity: 1, duration: 0.8, stagger: 0.1, ease: 'power3.out', delay: 0.4 }
      );
    }
  }

  // Initialize Vanilla Tilt if present
  if (typeof VanillaTilt !== 'undefined') {
    VanillaTilt.init(document.querySelectorAll(".glass:not(.auth-card), .feature-card"), {
      max: 5,
      speed: 400,
      glare: true,
      "max-glare": 0.1
    });
    
    // Auth card gets slightly heavier tilt
    VanillaTilt.init(document.querySelectorAll(".auth-card"), {
      max: 2,
      speed: 1000,
      glare: true,
      "max-glare": 0.05
    });
  }
});
