(() => {
  // ------------------------------------------------------------------
  // Configuración de endpoints (ajustar según entorno real)
  // ------------------------------------------------------------------
  const API_BASE = ''; // mismo dominio del orquestador
  const ENDPOINTS = {
    upload: '/v1/documents/upload',
    export: (id) => `/v1/documents/${id}/export?format=txt`,
    list: '/v1/documents',
  };

  // ------------------------------------------------------------------
  // Referencias DOM
  // ------------------------------------------------------------------
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const browseBtn = document.getElementById('browseBtn');
  const tokenInput = document.getElementById('tokenInput');
  const docTableBody = document.getElementById('docTableBody');
  const emptyState = document.getElementById('emptyState');
  const docCount = document.getElementById('docCount');
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');

  // ------------------------------------------------------------------
  // Estado
  // ------------------------------------------------------------------
  let documents = []; // { id, name, size, uploadedAt, status, text }

  // ------------------------------------------------------------------
  // Utilidades
  // ------------------------------------------------------------------
  function formatSize(bytes) {
    if (!bytes) return '—';
    const kb = bytes / 1024;
    if (kb < 1024) return `${Math.round(kb)} KB`;
    return `${(kb / 1024).toFixed(2)} MB`;
  }

  function formatTime(dateStr) {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
  }

  function showToast(msg, type = 'success') {
    toastMsg.textContent = msg;
    toast.classList.remove('translate-x-full');
    setTimeout(() => { toast.classList.add('translate-x-full'); }, 3000);
  }

  function renderTable() {
    docCount.textContent = `${documents.length} documento${documents.length !== 1 ? 's' : ''}`;

    if (documents.length === 0) {
      docTableBody.innerHTML = '';
      emptyState.classList.remove('hidden');
      return;
    }

    emptyState.classList.add('hidden');

    docTableBody.innerHTML = documents.map(doc => `
      <tr class="border-b border-gray-50 hover:bg-gray-50 transition-colors">
        <td class="px-6 py-4">
          <div class="font-medium text-gray-800">${escapeHtml(doc.name)}</div>
          <div class="text-xs text-gray-500 mt-1">${doc.id}</div>
        </td>
        <td class="px-6 py-4 text-gray-600">${formatSize(doc.size)}</td>
        <td class="px-6 py-4 text-gray-600">${formatTime(doc.uploadedAt)}</td>
        <td class="px-6 py-4">
          <span class="status-badge ${doc.status === 'procesando' ? 'status-procesando' : 'status-completado'}">
            ${doc.status === 'procesando'
              ? `<span class="w-3 h-3 border-2 border-current border-t-transparent rounded-full spinner mr-2"></span>En proceso`
              : `<span class="w-2 h-2 bg-green-500 rounded-full mr-2"></span>Completado`}
          </span>
        </td>
        <td class="px-6 py-4 text-right">
          ${doc.status === 'completado'
            ? `
              <button class="btn-copy btn-download mr-2 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded hover:bg-blue-700 flex items-center gap-1" onclick="app.downloadMarkdown('${doc.id}')">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Descargar .md
              </button>
              <button class="btn-copy px-3 py-1.5 bg-gray-100 text-gray-700 text-xs font-medium rounded hover:bg-gray-200 flex items-center gap-1" onclick="app.copyText('${doc.id}')">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"></path></svg>
                Copiar
              </button>
            `
            : `<span class="text-xs text-gray-400">—</span>`
          }
        </td>
      </tr>
    `).join('');
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function generateId() {
    return 'doc_' + Math.random().toString(36).substr(2, 9);
  }

  // ------------------------------------------------------------------
  // Drag & Drop
  // ------------------------------------------------------------------
  ['dragenter', 'dragover'].forEach(evt => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
  });

  ['dragleave', 'drop'].forEach(evt => {
    dropZone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length) handleFile(files[0]);
  });

  browseBtn.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length) handleFile(e.target.files[0]);
  });

  dropZone.addEventListener('click', () => fileInput.click());

  function handleFile(file) {
    if (!file.type.includes('pdf') && !file.name.toLowerCase().endsWith('.pdf')) {
      showToast('Solo se permiten archivos PDF', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showToast('El archivo supera los 10 MB', 'error');
      return;
    }

    const token = tokenInput.value.trim();
    if (!token) {
      showToast('Ingresa el token interno primero', 'error');
      return;
    }

    const id = generateId();
    const now = new Date().toISOString();

    documents.unshift({
      id,
      name: file.name,
      size: file.size,
      uploadedAt: now,
      status: 'procesando',
      text: null,
    });
    renderTable();

    // Llamada simulada al backend
    uploadDocument(file, token, id);
  }

  // ------------------------------------------------------------------
  // Funciones esqueleto (mock) — reemplazar con fetch real al backend
  // ------------------------------------------------------------------
  async function uploadDocument(file, token, docId) {
    try {
      // TODO: Conectar con backend real
      /*
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API_BASE}${ENDPOINTS.upload}`, {
        method: 'POST',
        headers: { 'X-Internal-Token': token },
        body: formData,
      });

      if (!res.ok) throw new Error(`Error ${res.status}`);
      const data = await res.json();

      const idx = documents.findIndex(d => d.id === docId);
      if (idx !== -1) {
        documents[idx] = { ...documents[idx], status: 'completado', text: data.text || '', id: data.id || docId };
        renderTable();
        showToast('Documento procesado correctamente');
      }
      */

      // Simulación de retraso de red
      await new Promise(r => setTimeout(r, 2500));

      const idx = documents.findIndex(d => d.id === docId);
      if (idx !== -1) {
        documents[idx] = {
          ...documents[idx],
          status: 'completado',
          text: 'Contenido extraído simulado del PDF: ' + documents[idx].name,
        };
        renderTable();
        showToast('Documento procesado correctamente');
      }
    } catch (err) {
      console.error(err);
      const idx = documents.findIndex(d => d.id === docId);
      if (idx !== -1) {
        documents[idx] = { ...documents[idx], status: 'error' };
        renderTable();
        showToast('Error al procesar el documento', 'error');
      }
    }
  }

  async function downloadMarkdown(docId) {
    const doc = documents.find(d => d.id === docId);
    if (!doc || !doc.text) return;

    try {
      // TODO: Conectar con backend real
      /*
      const token = tokenInput.value.trim();
      const res = await fetch(`${API_BASE}${ENDPOINTS.export(docId)}`, {
        headers: { 'X-Internal-Token': token },
      });
      const blob = await res.blob();
      */

      const blob = new Blob([doc.text || ''], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${doc.name.replace(/\.[^/.]+$/, '')}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('Archivo descargado');
    } catch (err) {
      console.error(err);
      showToast('Error al descargar', 'error');
    }
  }

  async function copyText(docId) {
    const doc = documents.find(d => d.id === docId);
    if (!doc || !doc.text) return;

    try {
      await navigator.clipboard.writeText(doc.text);
      showToast('Texto copiado al portapapeles');
    } catch (err) {
      doc.select ? doc.select() : null;
      document.execCommand('copy');
      showToast('Texto copiado al portapapeles');
    }
  }

  // ------------------------------------------------------------------
  // Inicialización
  // ------------------------------------------------------------------
  renderTable();

  // Exponer métodos globales para los botones inline
  window.app = { downloadMarkdown, copyText };
})();
