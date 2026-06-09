document.addEventListener('DOMContentLoaded', () => {
  // Extract CSRF token from page cookies securely
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  const csrfToken = getCookie('csrftoken');

  // --- 1. Inline Reply Form Toggling ---
  document.addEventListener('click', (e) => {
    // Open reply input
    if (e.target.closest('.toggle-reply-btn')) {
      const btn = e.target.closest('.toggle-reply-btn');
      const targetId = btn.getAttribute('data-target-id');
      const container = document.getElementById(`reply-form-${targetId}`);
      if (container) {
        container.style.display = 'block';
        const textarea = container.querySelector('textarea');
        if (textarea) textarea.focus();
      }
    }

    // Close reply input
    if (e.target.closest('.cancel-reply-btn')) {
      const btn = e.target.closest('.cancel-reply-btn');
      const targetId = btn.getAttribute('data-target-id');
      const container = document.getElementById(`reply-form-${targetId}`);
      if (container) container.style.display = 'none';
    }
  });

  // --- 2. Voting Logic (Upvote/Downvote) ---
  document.addEventListener('click', async (e) => {
    const voteBtn = e.target.closest('.vote-btn');
    if (!voteBtn) return;

    e.preventDefault();
    const messageId = voteBtn.getAttribute('data-message-id');
    const voteType = voteBtn.getAttribute('data-vote-type'); // 'upvote' or 'downvote'

    try {
      const response = await fetch(`/forum/messages/${messageId}/vote/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': csrfToken
        },
        body: new URLSearchParams({ 'vote_type': voteType })
      });

      if (!response.ok) throw new Error('Network error processing vote.');

      const data = await response.json();
      
      // Update score display
      const netScore = data.upvote_count - data.downvote_count;
      const countDisplay = document.getElementById(`vote-total-${messageId}`);
      if (countDisplay) countDisplay.textContent = netScore;

      // Visual active-state indicators
      const parentBlock = voteBtn.closest('.forum-message-voting');
      const upBtn = parentBlock.querySelector('.upvote-btn');
      const downBtn = parentBlock.querySelector('.downvote-btn');

      if (voteType === 'upvote') {
        upBtn.classList.toggle('active-upvote');
        downBtn.classList.remove('active-downvote');
      } else {
        downBtn.classList.toggle('active-downvote');
        upBtn.classList.remove('active-upvote');
      }
    } catch (error) {
      console.error("Voting error:", error);
    }
  });

  // --- 3. Follow / Unfollow Thread ---
  const followBtn = document.getElementById('follow-btn');
  if (followBtn) {
    followBtn.addEventListener('click', async () => {
      const pk = followBtn.dataset.threadPk;
      followBtn.disabled = true;

      try {
        const res = await fetch(`/forum/${pk}/follow/`, {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken },
        });
        const data = await res.json();

        if (data.is_following) {
          followBtn.textContent = '✓ Following';
          followBtn.classList.replace('btn--outline', 'btn--ghost');
          followBtn.dataset.following = 'true';
        } else {
          followBtn.textContent = '+ Follow';
          followBtn.classList.replace('btn--ghost', 'btn--outline');
          followBtn.dataset.following = 'false';
        }
        
        window.location.reload(); 
      } catch (err) {
        console.error('Follow toggle failed:', err);
      } finally {
        followBtn.disabled = false;
      }
    });
  }

  // --- 4. Pinning / Mark as Best Answer Logic ---
  document.addEventListener('click', async (e) => {
    const pinBtn = e.target.closest('.btn-pin-message');
    if (!pinBtn) return;

    const messageId = pinBtn.getAttribute('data-message-id');
    
    try {
      const response = await fetch(`/forum/messages/${messageId}/pin/`, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken }
      });

      if (response.ok) {
        // Reload to reflect new pinning order and badges
        window.location.reload(); 
      } else {
        const errorData = await response.json();
        alert(errorData.error || "Failed to update pin status.");
      }
    } catch (error) {
      console.error("Pinning error:", error);
    }
  });
});