(() => {
  const API_BASE = '';
  const INTERNAL_API_TOKEN = 'change-me-in-production';
  const ENDPOINTS = {
    upload: '/v1/documents/upload',
    export: (id) => `/v1/documents/${id}/export?format=txt`,
    list: '/v1/documents',
  };

  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');
  const browseBtn = document.getElementById('browseBtn');
  const docTableBody = document.getElementById('docTableBody');
  const emptyState = document.getElementById('emptyState');
  const docCount = document.getElementById('docCount');
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toastMsg');

  let documents = [];

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
    toast.className = type === 'error' ? 'toast toast-error show' : 'toast show';
    setTimeout(() => { toast.classList.remove('show'); }, 3500);
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function renderTable() {
    docCount.textContent = `${documents.length} documento${documents.length !== 1 ? 's' : ''}`;

    if (documents.length === 0) {
      docTableBody.innerHTML = '';
      emptyState.style.display = 'block';
      return;
    }

    emptyState.style.display = 'none';

    docTableBody.innerHTML = documents.map(doc => `
      <tr>
        <td>
          <div class="doc-name">${escapeHtml(doc.name)}</div>
          <div class="doc-id">${escapeHtml(doc.id || doc._id || '—')}</div>
        </td>
        <td class="doc-meta">${formatSize(doc.size)}</td>
        <td class="doc-meta">${formatTime(doc.uploadedAt || doc.created_at)}</td>
        <td>
          <span class="badge ${doc.status === 'procesando' ? 'badge-proc' : doc.status === 'error' ? 'badge-err' : 'badge-done'}">
            ${doc.status === 'procesando'
              ? `<span class="spinner"></span>En proceso`
              : doc.status === 'error'
                ? 'Error'
                : `<span style="width:8px;height:8px;background:var(--success);border-radius:50%;display:inline-block;margin-right:6px;"></span>Completado`}
          </span>
        </td>
        <td style="text-align:right">
          ${doc.status === 'completado'
            ? `
              <button class="btn btn-primary" data-action="download" data-doc-id="${escapeHtml(doc.id || doc._id)}">
                <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                Descargar .md
              </button>
              <button class="btn btn-ghost" data-action="copy" data-doc-id="${escapeHtml(doc.id || doc._id)}">
                <svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"></path></svg>
                Copiar
              </button>
            `
            : `<span class="doc-meta">—</span>`
          }
        </td>
      </tr>
    `).join('');
  }

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

    const id = 'doc_' + Math.random().toString(36).substr(2, 9);
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

    uploadDocument(file, id);
  }

  async function uploadDocument(file, docId) {
    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch(`${API_BASE}${ENDPOINTS.upload}`, {
        method: 'POST',
        body: formData,
      });

      if (res.status === 429) {
        throw new Error('Demasiadas solicitudes. Intente más tarde.');
      }
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Error ${res.status}`);
      }

      const data = await res.json();

      const idx = documents.findIndex(d => d.id === docId);
      if (idx !== -1) {
        documents[idx] = {
          ...documents[idx],
          status: 'completado',
          text: data.text || '',
          id: data.id || docId,
          size: data.size || file.size,
          uploadedAt: data.created_at || now,
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
        showToast(err.message || 'Error al procesar el documento', 'error');
      }
    }
  }

  async function downloadMarkdown(docId) {
    const doc = documents.find(d => d.id === docId);
    if (!doc) {
      showToast('Documento no encontrado', 'error');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}${ENDPOINTS.export(docId)}`, {
        headers: {
          'X-Internal-Token': INTERNAL_API_TOKEN,
        },
      });
      if (!res.ok) throw new Error(`Error ${res.status}`);
      const text = await res.text();

      const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(doc.name || 'documento').replace(/\.[^/.]+$/, '')}.md`;
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
    if (!doc || !doc.text) {
      showToast('No hay texto para copiar', 'error');
      return;
    }

    try {
      await navigator.clipboard.writeText(doc.text);
      showToast('Texto copiado al portapapeles');
    } catch (err) {
      try {
        const textarea = document.createElement('textarea');
        textarea.value = doc.text;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'absolute';
        textarea.style.left = '-9999px';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('Texto copiado al portapapeles');
      } catch (fallbackErr) {
        console.error(fallbackErr);
        showToast('Error al copiar', 'error');
      }
    }
  }

  docTableBody.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const docId = btn.getAttribute('data-doc-id');
    const action = btn.getAttribute('data-action');
    if (action === 'download') {
      downloadMarkdown(docId);
    } else if (action === 'copy') {
      copyText(docId);
    }
  });

  renderTable();

  window.app = { downloadMarkdown, copyText };
})();
