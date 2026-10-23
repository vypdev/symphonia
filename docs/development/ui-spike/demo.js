// Isolated visual fixture. No network, storage, or application-side effects.
const views = [...document.querySelectorAll('.view')];
const links = [...document.querySelectorAll('[data-section]')];
const validSections = new Set(views.map((view) => view.id));

function showSection() {
  const requested = window.location.hash.slice(1);
  const section = validSections.has(requested) ? requested : 'connections';
  for (const view of views) view.hidden = view.id !== section;
  for (const link of links) {
    if (link.dataset.section === section) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
  document.title = `${document.getElementById(`${section}-title`).textContent} · Symphonia UI fixture`;
}

window.addEventListener('hashchange', showSection);
showSection();

const themeToggle = document.getElementById('theme-toggle');
themeToggle.addEventListener('click', () => {
  const dark = document.documentElement.classList.toggle('theme-dark');
  themeToggle.setAttribute('aria-label', `Switch to ${dark ? 'light' : 'dark'} theme`);
  themeToggle.title = `Switch to ${dark ? 'light' : 'dark'} theme`;
});
