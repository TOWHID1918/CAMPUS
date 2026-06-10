/* lightbox.js */

document.addEventListener('DOMContentLoaded', function () {
  var lightbox = document.getElementById('lightbox');
  var lightboxImg = document.getElementById('lightbox-img');

  if (!lightbox || !lightboxImg) return;

  // --- 1. DYNAMICALLY CREATE BUTTONS ---
  var closeBtn = document.createElement('button');
  closeBtn.className = 'lightbox-close';
  closeBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 384 512" width="18" height="18" fill="currentColor"><path d="M342.6 150.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L192 210.7 86.6 105.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L146.7 256 41.4 361.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L192 301.3 297.4 406.6c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L237.3 256 342.6 150.6z"/></svg>';
  lightbox.appendChild(closeBtn);

  var dlBtn = document.createElement('a');
  dlBtn.className = 'lightbox-download';
  dlBtn.title = "Download Image";
  dlBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="18" height="18" fill="currentColor"><path d="M288 32c0-17.7-14.3-32-32-32s-32 14.3-32 32V274.7l-73.4-73.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3l128 128c12.5 12.5 32.8 12.5 45.3 0l128-128c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L288 274.7V32zM64 352c-35.3 0-64 28.7-64 64v32c0 35.3 28.7 64 64 64H448c35.3 0 64-28.7 64-64V416c0-35.3-28.7-64-64-64H346.5l-45.3 45.3c-25 25-65.5 25-90.5 0L165.5 352H64zm368 56a24 24 0 1 1 0 48 24 24 0 1 1 0-48z"/></svg>';
  lightbox.appendChild(dlBtn);

  // --- 2. PAN & ZOOM STATE VARIABLES ---
  var isZoomed = false;
  var isDragging = false;
  var hasDragged = false; 
  var startX = 0, startY = 0;
  var translateX = 0, translateY = 0;
  var currentScale = 1;

  function applyTransform() {
    lightboxImg.style.transform = `translate(${translateX}px, ${translateY}px) scale(${currentScale})`;
  }

  // --- 3. MASTER INTERCEPTOR (Opens Lightbox) ---
  function interceptImage(e) {
    var target = e.target;
    var parentLink = target.closest('a');
    var img = target.closest('img');

    // Chatbox padding support
    if (!img && parentLink) {
      var isExplicitMediaLink = parentLink.href && (parentLink.href.match(/\.(jpeg|jpg|gif|png|webp|svg)(\?.*)?$/i) || parentLink.href.includes('/media/'));
      if (isExplicitMediaLink) {
        img = parentLink.querySelector('img');
      }
    }

    if (!img) return; 
    if (img.id === 'lightbox-img') return; 

    // --- THE DASHBOARD BUG FIX ---
    
    // Rule 1: If the image is explicitly wrapped in a web link (like to another page), let it navigate.
    if (parentLink && parentLink.href) {
      var isMedia = parentLink.href.match(/\.(jpeg|jpg|gif|png|webp|svg)(\?.*)?$/i) || parentLink.href.includes('/media/');
      if (!isMedia && !parentLink.href.startsWith('javascript:') && !parentLink.href.startsWith('#')) {
        return; // Abort lightbox, follow the link!
      }
    }

    // Rule 2: If the image is inside a preview card (Marketplace/Lost&Found Dashboard), skip it!
    var parentCard = img.closest('.card');
    if (parentCard) {
      var isPreviewCard = Array.from(parentCard.querySelectorAll('a, button, .btn')).some(function(el) {
        var txt = (el.innerText || '').toLowerCase();
        return txt.includes('view details') || txt.includes('view discussion') || txt.includes('view post');
      });
      if (isPreviewCard) return; // Abort lightbox, let the user click the card to open details!
    }
    // -----------------------------

    e.preventDefault();
    e.stopPropagation();
    e.stopImmediatePropagation();

    if (e.type === 'click') {
      var imgSrc = img.src;
      if (parentLink && parentLink.href && (parentLink.href.match(/\.(jpeg|jpg|gif|png|webp|svg)(\?.*)?$/i) || parentLink.href.includes('/media/'))) {
        imgSrc = parentLink.href;
      }

      // Set image source
      lightboxImg.src = imgSrc;
      
      // Update download button link
      dlBtn.href = imgSrc;
      var filename = imgSrc.split('/').pop().split('?')[0] || 'campus-image.jpg';
      dlBtn.download = filename;

      lightbox.style.display = 'flex';
      void lightbox.offsetWidth; 
      lightbox.classList.add('is-visible');
      document.body.style.overflow = 'hidden';
      
      lightboxImg.style.transition = 'transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
    }
  }

  // Intercept all phases
  document.addEventListener('click', interceptImage, true);
  document.addEventListener('mousedown', interceptImage, true);
  document.addEventListener('mouseup', interceptImage, true);

  // --- 4. DRAG TO PAN LOGIC ---
  lightboxImg.addEventListener('mousedown', function(e) {
    if (isZoomed) {
      e.preventDefault(); 
      isDragging = true;
      hasDragged = false;
      lightboxImg.classList.add('is-dragging');
      
      startX = e.clientX - translateX;
      startY = e.clientY - translateY;
    }
  });

  window.addEventListener('mousemove', function(e) {
    if (isDragging) {
      hasDragged = true; 
      translateX = e.clientX - startX;
      translateY = e.clientY - startY;
      applyTransform();
    }
  });

  window.addEventListener('mouseup', function() {
    if (isDragging) {
      isDragging = false;
      lightboxImg.classList.remove('is-dragging');
    }
  });

  // --- 5. CLICK TO ZOOM IN / OUT ---
  lightboxImg.addEventListener('click', function(e) {
    e.stopPropagation(); 

    if (hasDragged) {
      hasDragged = false;
      return;
    }

    if (!isZoomed) {
      lightboxImg.style.transition = 'transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
      
      var rect = lightboxImg.getBoundingClientRect();
      var x = ((e.clientX - rect.left) / rect.width) * 100;
      var y = ((e.clientY - rect.top) / rect.height) * 100;

      lightboxImg.style.transformOrigin = `${x}% ${y}%`;
      currentScale = 2.5; 
      translateX = 0;
      translateY = 0;
      applyTransform();

      lightboxImg.classList.add('is-zoomed');
      isZoomed = true;
    } else {
      lightboxImg.style.transition = 'transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94)';
      currentScale = 1;
      translateX = 0;
      translateY = 0;
      applyTransform();

      lightboxImg.classList.remove('is-zoomed');
      isZoomed = false;
    }
  });

  // --- 6. CLOSE FUNCTIONALITY ---
  function closeLightbox() {
    lightbox.classList.remove('is-visible');
    
    lightboxImg.classList.remove('is-zoomed', 'is-dragging');
    isZoomed = false;
    isDragging = false;
    hasDragged = false;
    currentScale = 1;
    translateX = 0;
    translateY = 0;
    applyTransform();

    setTimeout(function() {
      lightbox.style.display = 'none';
      lightboxImg.src = ''; 
      dlBtn.href = '';
      lightboxImg.style.transformOrigin = 'center center'; 
      document.body.style.overflow = ''; 
    }, 300);
  }

  lightbox.addEventListener('click', function (e) {
    if (e.target === lightbox) closeLightbox();
  });

  closeBtn.addEventListener('click', function(e) {
    e.stopPropagation();
    closeLightbox();
  });
  
  dlBtn.addEventListener('click', function(e) {
    e.stopPropagation();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && lightbox.style.display === 'flex') closeLightbox();
  });
});