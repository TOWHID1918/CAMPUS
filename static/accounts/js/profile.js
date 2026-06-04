/* profile.js — Edit-page only.
   The skill chip picker has been removed — skills are now managed
   on the dedicated /skills/add/ page with server-side forms.
   Only the photo upload preview remains here.
*/

function previewPhoto(input) {
  var file = input.files[0];
  if (!file) return;

  var img      = document.getElementById('e-photoPreviewImg');
  var initials = document.getElementById('e-photoInitials');
  var filename = document.getElementById('e-photoFilename');

  if (img) {
    img.src           = URL.createObjectURL(file);
    img.style.display = '';
  }
  if (initials) initials.style.display = 'none';
  if (filename) filename.textContent   = file.name;
}