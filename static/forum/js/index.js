// apps/forum/static/forum/js/forum.js

document.addEventListener('DOMContentLoaded', () => {
  const fuzzyInput = document.getElementById('fuzzy-search-input');
  const suggestionsBox = document.getElementById('search-suggestions-box');
  const searchWrapper = document.getElementById('search-input-wrapper');

  let debounceTimer;

  if (fuzzyInput) {
    fuzzyInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      const query = fuzzyInput.value.trim();
      if (query.length < 2) { suggestionsBox.style.display = 'none'; return; }

      debounceTimer = setTimeout(async () => {
        const response = await fetch(`/forum/search-suggestions/?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        renderSuggestions(data);
      }, 250);
    });
  }

  function renderSuggestions(data) {
    suggestionsBox.innerHTML = '';
    let hasResults = false;

    const activeParams = new URLSearchParams(window.location.search);

    const sections = [
      { title: 'Departments', items: data.departments, type: 'dept' },
      { title: 'Courses',     items: data.courses,     type: 'course' },
      { title: 'Users',       items: data.users,       type: 'user' }
    ];

    sections.forEach(section => {
      if (section.items.length > 0) {
        hasResults = true;

        const head = document.createElement('div');
        head.className = 'suggestion-header';
        head.textContent = section.title;
        suggestionsBox.appendChild(head);

        section.items.forEach(item => {
          const paramKey   = { dept: 'department', course: 'course', user: 'user' }[section.type];
          const paramValue = section.type === 'user' ? item.handle : item.code;
          const alreadyActive = activeParams.getAll(paramKey).includes(paramValue);

          const div = document.createElement('div');
          div.className = 'suggestion-item' + (alreadyActive ? ' suggestion-item--active' : '');
          div.textContent = item.label + (alreadyActive ? ' ✓' : '');

          // Clicking an already-active suggestion is a no-op
          if (!alreadyActive) {
            div.onclick = () => applyFilter(section.type, item);
          }

          suggestionsBox.appendChild(div);
        });
      }
    });

    suggestionsBox.style.display = hasResults ? 'block' : 'none';
  }

  function applyFilter(type, item) {
    const params   = new URLSearchParams(window.location.search);
    const paramKey = { dept: 'department', course: 'course', user: 'user' }[type];
    const paramValue = type === 'user' ? item.handle : item.code;

    // Guard: don't stack a duplicate value
    if (params.getAll(paramKey).includes(paramValue)) {
      suggestionsBox.style.display = 'none';
      return;
    }

    // append() stacks values; set() would overwrite the previous one
    params.append(paramKey, paramValue);
    window.location.search = params.toString();
  }

  // Close when clicking outside the wrapper (input + dropdown together),
  // so a click on a suggestion item doesn't race with this handler.
  document.addEventListener('click', (e) => {
    if (searchWrapper && !searchWrapper.contains(e.target)) {
      suggestionsBox.style.display = 'none';
    }
  });
});