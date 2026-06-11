/* ── Listing List ─────────────────────────────────────────── */
function initListingList() {
  document.getElementById('categoryFilter').addEventListener('change', applyListingFilters);
  document.getElementById('sortFilter').addEventListener('change', applyListingFilters);
  document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') applyListingFilters();
  });

  function applyListingFilters() {
    const category = document.getElementById('categoryFilter').value;
    const sort     = document.getElementById('sortFilter').value;
    const search   = document.getElementById('searchInput').value.trim();
    const params   = new URLSearchParams();
    if (category) params.set('category', category);
    if (sort !== 'newest') params.set('sort', sort);
    if (search) params.set('search', search);
    window.location.href = listingListUrl + '?' + params.toString();
  }

  const cards = document.querySelectorAll('.post-card');
  const count = document.getElementById('filterCount');
  if (count) count.textContent = cards.length + ' listing' + (cards.length !== 1 ? 's' : '');
}

/* ── My Listings ──────────────────────────────────────────── */
function initMyListings() {
  document.getElementById('categoryFilter').addEventListener('change', applyMyListingFilters);
  document.getElementById('sortFilter').addEventListener('change', applyMyListingFilters);
  document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') applyMyListingFilters();
  });

  function applyMyListingFilters() {
    const category = document.getElementById('categoryFilter').value;
    const sort     = document.getElementById('sortFilter').value;
    const search   = document.getElementById('searchInput').value.trim();
    const params   = new URLSearchParams();
    if (category) params.set('category', category);
    if (sort !== 'newest') params.set('sort', sort);
    if (search) params.set('search', search);
    window.location.href = myListingsUrl + '?' + params.toString();
  }

  const cards = document.querySelectorAll('.post-card');
  const count = document.getElementById('filterCount');
  if (count) count.textContent = cards.length + ' listing' + (cards.length !== 1 ? 's' : '');
}

/* ── Orders Buyer ───────────────────────────────────── */
function initOrdersBuyer() {
  document.getElementById('categoryFilter').addEventListener('change', applyOrderFilters);
  document.getElementById('sortFilter').addEventListener('change', applyOrderFilters);
  document.getElementById('searchInput').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') applyOrderFilters();
  });

  function applyOrderFilters() {
    const category = document.getElementById('categoryFilter').value;
    const sort     = document.getElementById('sortFilter').value;
    const search   = document.getElementById('searchInput').value.trim();
    const params   = new URLSearchParams();
    if (category) params.set('category', category);
    if (sort !== 'newest') params.set('sort', sort);
    if (search) params.set('search', search);
    window.location.href = ordersBuyerUrl + '?' + params.toString();
  }

  const cards = document.querySelectorAll('.post-card');
  const count = document.getElementById('filterCount');
  if (count) count.textContent = cards.length + ' listing' + (cards.length !== 1 ? 's' : '');
}