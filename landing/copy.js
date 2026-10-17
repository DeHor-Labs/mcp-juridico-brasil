document.querySelectorAll('.copy').forEach((btn) => {
  btn.addEventListener('click', async () => {
    const text = btn.parentElement.querySelector('code').textContent;
    try {
      await navigator.clipboard.writeText(text);
      btn.textContent = 'Copiado';
      btn.dataset.ok = '';
    } catch {
      btn.textContent = 'Selecione e copie';
    }
    setTimeout(() => { btn.textContent = 'Copiar'; delete btn.dataset.ok; }, 1800);
  });
});
