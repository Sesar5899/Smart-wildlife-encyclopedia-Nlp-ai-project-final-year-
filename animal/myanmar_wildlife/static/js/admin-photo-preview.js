/* Content Studio photo pickers: show the chosen image(s) before the form is saved. */
const ALLOWED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const PHOTO_TYPE_ERROR = 'JPEG, PNG သို့မဟုတ် WebP ဓာတ်ပုံကိုသာ တင်နိုင်ပါသည်။';
const previewObjectUrls = [];

function photoPreviewUrl(file) {
    const url = URL.createObjectURL(file);
    previewObjectUrls.push(url);
    return url;
}

window.addEventListener('pagehide', () => previewObjectUrls.forEach(url => URL.revokeObjectURL(url)));

function newPhotoBadge() {
    const badge = document.createElement('span');
    badge.className = 'admin-photo-badge';
    badge.textContent = 'အသစ်';
    return badge;
}

function newPhotoThumb(file) {
    const figure = document.createElement('figure');
    figure.className = 'admin-photo-new';
    const image = document.createElement('img');
    image.src = photoPreviewUrl(file);
    image.alt = file.name;
    figure.append(image, newPhotoBadge());
    return figure;
}

function setupPhotoPreview(input) {
    const scope = input.closest('.admin-photo-slot, .admin-cover-details, .admin-photo-card');
    if (!scope) return;
    const gallery = scope.querySelector('.admin-photo-gallery-preview');
    const preview = gallery || scope.querySelector('.admin-photo-preview');
    if (!preview) return;
    const placeholder = gallery ? gallery.querySelector('.admin-photo-preview') : null;
    const removeCheckbox = scope.querySelector('.admin-check input[type="checkbox"]');
    const originalHtml = preview.innerHTML;

    const note = document.createElement('p');
    note.className = 'admin-upload-note';
    note.setAttribute('role', 'status');
    const noteText = document.createElement('span');
    const clearButton = document.createElement('button');
    clearButton.type = 'button';
    clearButton.textContent = 'ဖျက်ရန်';
    clearButton.title = 'ရွေးထားသည့် ဓာတ်ပုံကို ပြန်ဖျက်ရန်';
    note.append(noteText, clearButton);
    input.closest('.admin-upload').after(note);

    function showNote(message, isError) {
        noteText.textContent = message;
        note.classList.toggle('is-error', Boolean(isError));
        note.classList.add('is-visible');
    }

    function render() {
        const files = Array.from(input.files || []);
        const valid = files.filter(file => ALLOWED_PHOTO_TYPES.includes(file.type));
        const rejected = files.filter(file => !ALLOWED_PHOTO_TYPES.includes(file.type));

        if (gallery) {
            gallery.querySelectorAll('.admin-photo-new').forEach(thumb => thumb.remove());
            valid.forEach(file => gallery.append(newPhotoThumb(file)));
            if (placeholder) placeholder.classList.toggle('admin-photo-hidden', valid.length > 0);
        } else if (valid.length) {
            preview.innerHTML = '';
            const image = document.createElement('img');
            image.src = photoPreviewUrl(valid[0]);
            image.alt = valid[0].name;
            preview.append(image, newPhotoBadge());
            preview.classList.add('is-pending');
        } else {
            preview.innerHTML = originalHtml;
            preview.classList.remove('is-pending');
        }

        if (rejected.length) showNote(PHOTO_TYPE_ERROR, true);
        else if (!files.length) {
            note.classList.remove('is-visible', 'is-error');
            noteText.textContent = '';
        }
        else if (files.length > 1) showNote(`ဓာတ်ပုံ ${valid.length} ပုံ ရွေးထားသည်`, false);
        else showNote(files[0].name, false);

        // A new pick and the "remove" checkbox contradict each other on single
        // slots, where the server keeps the removal — so only one may be active.
        if (removeCheckbox && !gallery && valid.length) removeCheckbox.checked = false;
        if (removeCheckbox) preview.classList.toggle('is-removing', removeCheckbox.checked);
    }

    input.addEventListener('change', render);
    clearButton.addEventListener('click', () => {
        input.value = '';
        render();
    });
    if (removeCheckbox) {
        removeCheckbox.addEventListener('change', () => {
            if (removeCheckbox.checked && !gallery) input.value = '';
            render();
        });
    }
    render();
}

document.querySelectorAll('.admin-upload input[type="file"]').forEach(setupPhotoPreview);
