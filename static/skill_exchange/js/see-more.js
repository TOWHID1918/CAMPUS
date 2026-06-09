document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.sx-partner-message-wrap').forEach(function (wrap) {
        const textEl = wrap.querySelector('.sx-partner-message-text');
        const btn    = wrap.querySelector('.sx-see-more-btn');
        const label  = wrap.querySelector('.sx-see-more-label');
        const icon   = wrap.querySelector('.sx-see-more-icon');

        function checkClamp() {
    
    if (textEl.classList.contains('is-expanded')) return;
    
    const isClamped = textEl.scrollHeight > textEl.clientHeight + 2;
    btn.classList.toggle('visible', isClamped);
}

        requestAnimationFrame(checkClamp);

        new ResizeObserver(checkClamp).observe(textEl);

        btn.addEventListener('click', function () {
            const expanded = textEl.classList.toggle('is-expanded');
            label.textContent = expanded ? 'See less' : 'See more';
            icon.textContent  = expanded ? '▴' : '▾';
        });
    });
});