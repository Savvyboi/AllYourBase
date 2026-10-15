document.querySelectorAll('[data-filter]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));
document.querySelectorAll('[data-status]').forEach(c=>c.hidden=b.dataset.filter!=='all'&&c.dataset.status!==b.dataset.filter);
}));
