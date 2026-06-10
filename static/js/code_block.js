/* code_block.js */

document.addEventListener('DOMContentLoaded', function () {
  
  var codeBlockRegex = /```([a-zA-Z0-9+#-]+)?([\s\S]*?)```/g;

  function decodeEntities(html) {
    var txt = document.createElement("textarea");
    txt.innerHTML = html;
    return txt.value;
  }

  function formatCodeBlocks(element) {
    
    var allElements = element.querySelectorAll('div, p, span');
    
    var contentAreas = Array.from(allElements).filter(function(el) {
      // Must contain backticks to proceed
      if (!el.innerHTML.includes('```')) return false;
      
      // Skip main structural pieces
      if (el.tagName.toLowerCase() === 'nav' || el.tagName.toLowerCase() === 'main') return false;
      if (el.querySelector('nav, main, section, form')) return false;

      // --- PREVIEW BLOCKER: Protects the Front Page & Forum List ---
      // If the text is inside a card that contains a "View Discussion" link, 
      // it is a preview snippet. Skip formatting so it looks like normal text!
      var parentCard = el.closest('.card');
      if (parentCard) {
        var isPreviewCard = Array.from(parentCard.querySelectorAll('a')).some(function(link) {
          var txt = link.innerText.toLowerCase();
          return txt.includes('view discussion') || txt.includes('view post') || txt.includes('view thread');
        });
        
        if (isPreviewCard) return false; // Abort formatting!
      }
      // -------------------------------------------------------------

      var className = (el.className || "").toLowerCase();
      
      if (el.tagName.toLowerCase() === 'p') return true;

      if (className.includes('message') || className.includes('chat') || className.includes('content') || className.includes('body') || className.includes('desc') || className.includes('thread') || className.includes('comment') || className.includes('text')) {
        return true;
      }
      return false;
    });
    
    contentAreas.forEach(function(el) {
      if (el.dataset.codeFormatted === "true") return;

      var html = el.innerHTML;
      
      var newHtml = html.replace(codeBlockRegex, function(match, language, code) {
        var langDisplay = language ? language : 'Code';
        var langClass = language ? 'language-' + language.toLowerCase() : '';
        
        var cleanCode = code.replace(/&nbsp;/g, ' '); 
        cleanCode = cleanCode.replace(/<br\s*\/?>/gi, '\n'); 
        cleanCode = cleanCode.replace(/<\/p>\s*<p>/gi, '\n'); 
        cleanCode = cleanCode.replace(/<[^>]+>/g, ''); 
        cleanCode = cleanCode.trim();
        cleanCode = cleanCode.replace(/^\n+|\n+$/g, ''); 

        var copyText = decodeEntities(cleanCode);
        
        return `<div class="code-block-wrapper"><div class="code-block-header"><span class="code-block-lang">${langDisplay}</span><button class="code-block-copy" data-code="${encodeURIComponent(copyText)}">Copy</button></div><pre><code class="${langClass}">${cleanCode}</code></pre></div>`;
      });
      
      el.innerHTML = newHtml;
      el.dataset.codeFormatted = "true";

      // Cleanup stray Django paragraph tags
      el.querySelectorAll('p').forEach(function(p) {
        var content = p.innerHTML.trim();
        if (content === '' || content === '<br>' || content === '&nbsp;') {
          p.remove();
        }
      });

      if (typeof hljs !== 'undefined') {
        el.querySelectorAll('pre code').forEach(function(block) {
          hljs.highlightElement(block);
        });
      }
    });
  }

  formatCodeBlocks(document.body);

  var observer = new MutationObserver(function(mutations) {
    mutations.forEach(function(mutation) {
      mutation.addedNodes.forEach(function(node) {
        if (node.nodeType === 1) formatCodeBlocks(node);
      });
    });
  });

  observer.observe(document.body, { childList: true, subtree: true });

  document.body.addEventListener('click', function(e) {
    if (e.target.classList.contains('code-block-copy')) {
      var btn = e.target;
      var codeToCopy = decodeURIComponent(btn.getAttribute('data-code'));
      
      navigator.clipboard.writeText(codeToCopy).then(function() {
        var originalText = btn.innerText;
        btn.innerText = 'Copied!';
        btn.classList.add('copied');
        
        setTimeout(function() {
          btn.innerText = originalText;
          btn.classList.remove('copied');
        }, 2000);
      });
    }
  });
});