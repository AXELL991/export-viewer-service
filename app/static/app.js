(() => {
  const TOKEN_KEY = 'pdf_extractor_token';
  const API_BASE = '';

  const tokenInput = document.getElementById('token');
  const fileInput = document.getElementById('file');
  const btnExtract = document.getElementById('btnExtract');
  const resultCard = document.getElementById('resultCard');
  const metaFile = document.getElementById('metaFile');
  const metaPages = document.getElementById('metaPages');
  const output = document.getElementById('output');
  const btnDownload = document.getElementById('btnDownload');
  const btnCopy = document.getElementById('btnCopy');
  const alertError = document.getElementById('alert-error');
  const alertSuccess = document.getElementById('alert-success');

  let currentDoc = null;

  function showError(msg) {
    alertError.textContent = msg;
    alertError.style.display = 'block';
    alertSuccess.style.display = 'none';
  }

  function showSuccess(msg) {
    alertSuccess.textContent = msg;
    alertSuccess.style.display = 'block';
    alertError.style.display = 'none';
  }

  function hideAlerts() {
    alertError.style.display = 'none';
    alertSuccess.style.display = 'none';
  }

  function loadToken() {
    const saved = localStorage.getItem(TOKEN_KEY);
    if (saved) tokenInput.value = saved;
  }

  function saveToken() {
    localStorage.setItem(TOKEN_KEY, tokenInput.value.trim());
  }

  function validate() {
    const hasToken = tokenInput.value.trim().length > 0;
    const hasFile = fileInput.files.length > 0;
    btnExtract.disabled = !(hasToken && hasFile);
  }

  async function extractPdf() {
    hideAlerts();
    const token = tokenInput.value.trim();
    const file = fileInput.files[0];
    saveToken();

    const formData = new FormData();
    formData.append('file', file);

    btnExtract.disabled = true;
    btnExtract.textContent = 'Procesando...';

    try {
      const res = await fetch(`${API_BASE}/v1/documents/upload`, {
        method: 'POST',
        headers: { 'X-Internal-Token': token },
        body: formData,
      });

      if (res.status === 401) {
        throw new Error('Token interno invalido. Verifica el token e intenta de nuevo.');
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Error ${res.status} al subir el PDF`);
      }

      const data = await res.json();
      currentDoc = data;

      metaFile.textContent = data.filename || '-';
      metaPages.textContent = data.pages || '-';
      output.value = data.text || '';

      resultCard.classList.remove('hidden');
      btnDownload.disabled = false;
      showSuccess('PDF extraido correctamente.');
    } catch (err) {
      showError(err.message);
      console.error(err);
    } finally {
      btnExtract.disabled = false;
      btnExtract.textContent = 'Extraer texto';
    }
  }

  function downloadMarkdown() {
    if (!currentDoc) return;
    const name = (currentDoc.filename || 'documento').replace(/\.[^/.]+$/, '');
    const pages = currentDoc.pages || 0;
    const text = currentDoc.text || '';

    const md = [
      `# ${name}`,
      ``,
      `Paginas: ${pages}`,
      ``,
      `## Contenido extraido`,
      ``,
      text,
      ``,
    ].join('\n');

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showSuccess(`Archivo ${name}.md descargado.`);
  }

  async function copyToClipboard() {
    const text = output.value;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      showSuccess('Texto copiado al portapapeles.');
    } catch (err) {
      output.select();
      document.execCommand('copy');
      showSuccess('Texto copiado al portapapeles.');
    }
  }

  tokenInput.addEventListener('input', validate);
  fileInput.addEventListener('change', validate);
  btnExtract.addEventListener('click', extractPdf);
  btnDownload.addEventListener('click', downloadMarkdown);
  btnCopy.addEventListener('click', copyToClipboard);

  loadToken();
  validate();
})();
