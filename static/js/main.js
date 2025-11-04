// Tema persistente
const toggleTheme = () => {
  const html = document.documentElement;
  const theme = html.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-bs-theme', theme);
  localStorage.setItem('theme', theme);
};
if (localStorage.getItem('theme') === 'dark') {
  document.documentElement.setAttribute('data-bs-theme', 'dark');
}