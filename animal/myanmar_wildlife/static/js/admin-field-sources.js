(() => {
    'use strict';

    const form = document.querySelector('form.admin-editor');
    const editor = document.getElementById('sourceEditor');
    const addButton = document.getElementById('addSourceButton');
    const dataElement = document.getElementById('fieldSourceData');
    if (!form || !editor || !addButton || !dataElement) return;

    const data = JSON.parse(dataElement.textContent);
    const states = [];

    function validHttpUrl(raw) {
        try {
            const parsed = new URL(raw);
            return ['http:', 'https:'].includes(parsed.protocol) && Boolean(parsed.hostname);
        } catch (_) {
            return false;
        }
    }

    function sourceRows() {
        const seen = new Set();
        return [...editor.querySelectorAll('.admin-source-row')].map(row => ({
            label: row.querySelector('[name="source_label"]').value.trim(),
            url: row.querySelector('[name="source_url_item"]').value.trim()
        })).filter(source => {
            if (!validHttpUrl(source.url) || seen.has(source.url)) return false;
            seen.add(source.url);
            return true;
        });
    }

    function makeSourceRow(label = '', url = '') {
        const row = document.createElement('div');
        row.className = 'admin-source-row';
        const title = document.createElement('label');
        const titleText = document.createElement('span');
        titleText.innerHTML = 'ရင်းမြစ်အမည် <code class="admin-field-name">source_label</code>';
        const titleInput = document.createElement('input');
        titleInput.name = 'source_label';
        titleInput.placeholder = 'ဥပမာ — IUCN Red List';
        titleInput.value = label;
        title.append(titleText, titleInput);

        const link = document.createElement('label');
        link.className = 'admin-source-url';
        const linkText = document.createElement('span');
        linkText.innerHTML = 'Source URL <code class="admin-field-name">source_url_item</code>';
        const linkInput = document.createElement('input');
        linkInput.type = 'url';
        linkInput.name = 'source_url_item';
        linkInput.placeholder = 'https://...';
        linkInput.value = url;
        link.append(linkText, linkInput);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'admin-source-remove';
        remove.setAttribute('aria-label', 'ရင်းမြစ် ဖယ်ရှားရန်');
        remove.textContent = '×';
        row.append(title, link, remove);
        return row;
    }

    function renderLinks(state) {
        const selected = [...state.select.selectedOptions];
        state.links.replaceChildren();
        if (!selected.length) {
            const empty = document.createElement('span');
            empty.className = 'admin-inline-source-empty';
            empty.textContent = 'မူရင်း source မချိတ်ထားသေးပါ';
            state.links.append(empty);
            return;
        }
        selected.forEach(option => {
            const chip = document.createElement('span');
            chip.className = 'admin-inline-source-chip';
            const link = document.createElement('a');
            link.href = option.value;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = option.textContent || option.value;
            link.title = option.value;

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.className = 'admin-inline-source-unlink';
            remove.textContent = '×';
            remove.title = 'ဤ field နှင့် source ချိတ်ဆက်မှုကို ဖြုတ်ရန်';
            remove.setAttribute(
                'aria-label',
                `${option.textContent || option.value} source ချိတ်ဆက်မှုကို ဖြုတ်ရန်`
            );
            remove.addEventListener('click', () => {
                option.selected = false;
                state.select.dispatchEvent(new Event('change'));
            });

            chip.append(link, remove);
            state.links.append(chip);
        });
    }

    function syncOptions() {
        const sources = sourceRows();
        states.forEach(state => {
            const selected = state.initialSelection || new Set(
                [...state.select.selectedOptions].map(option => option.value)
            );
            state.select.replaceChildren(...sources.map(source => {
                const option = new Option(source.label || source.url, source.url);
                option.selected = selected.has(source.url);
                return option;
            }));
            state.initialSelection = null;
            renderLinks(state);
        });
    }

    function attachField(field, fieldLabel) {
        const control = form.querySelector(`[name="${field}"]`);
        const label = control && control.closest('label');
        if (!label || !label.parentElement.classList.contains('admin-form-grid')) return;

        const group = document.createElement('div');
        group.className = 'admin-field-with-source';
        if (label.classList.contains('admin-field-wide')) {
            label.classList.remove('admin-field-wide');
            group.classList.add('admin-field-wide');
        }
        label.replaceWith(group);
        group.append(label);

        const box = document.createElement('div');
        box.className = 'admin-inline-source';
        const links = document.createElement('div');
        links.className = 'admin-inline-source-links';

        const details = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = 'ဤအချက်၏ source ရွေးရန် / ထည့်ရန်';
        const selectLabel = document.createElement('label');
        selectLabel.textContent = `${fieldLabel} ၏ source`;
        const select = document.createElement('select');
        select.name = `field_source.${field}`;
        select.className = 'field-source-select';
        select.multiple = true;
        select.size = 3;
        select.setAttribute('aria-label', `${fieldLabel} ၏ source များ`);
        selectLabel.append(select);

        const hint = document.createElement('small');
        hint.textContent = 'Source အများကြီးရွေးရန် Ctrl / ⌘ ကို ဖိထားပါ။';
        const addLine = document.createElement('div');
        addLine.className = 'admin-inline-source-add';
        const urlInput = document.createElement('input');
        urlInput.type = 'text';
        urlInput.inputMode = 'url';
        urlInput.placeholder = 'Source URL အသစ် — https://...';
        urlInput.setAttribute('aria-label', `${fieldLabel} အတွက် source URL အသစ်`);
        const addLink = document.createElement('button');
        addLink.type = 'button';
        addLink.textContent = 'ဒီအချက်မှာ ချိတ်ရန်';
        addLine.append(urlInput, addLink);

        const warning = document.createElement('small');
        warning.className = 'admin-inline-source-warning';
        warning.hidden = true;
        warning.textContent = 'အချက်ကို ပြင်ထားသဖြင့် ယခင် source ကို ပြန်စစ်ပြီး ရွေးပါ။';

        const confirmed = document.createElement('input');
        confirmed.type = 'hidden';
        confirmed.name = `field_source_confirmed.${field}`;

        details.append(summary, selectLabel, hint, addLine);
        box.append(links, details, warning, confirmed);
        group.append(box);

        const state = {
            control, select, links, warning, confirmed,
            lastLinkedValue: control.value,
            initialSelection: new Set(data.mapping[field] || [])
        };
        states.push(state);

        const invalidateIfChanged = () => {
            if (control.value === state.lastLinkedValue) return;
            if (select.selectedOptions.length) {
                [...select.options].forEach(option => { option.selected = false; });
                confirmed.value = '';
                warning.hidden = false;
                renderLinks(state);
            }
            state.lastLinkedValue = control.value;
        };
        control.addEventListener('input', invalidateIfChanged);
        control.addEventListener('change', invalidateIfChanged);
        select.addEventListener('change', () => {
            confirmed.value = select.selectedOptions.length ? '1' : '';
            state.lastLinkedValue = control.value;
            warning.hidden = true;
            renderLinks(state);
        });
        addLink.addEventListener('click', () => {
            const url = urlInput.value.trim();
            if (!validHttpUrl(url)) {
                urlInput.setCustomValidity('http/https URL အပြည့်အစုံ ထည့်ပါ။');
                urlInput.reportValidity();
                return;
            }
            urlInput.setCustomValidity('');
            if (!sourceRows().some(source => source.url === url)) {
                editor.append(makeSourceRow(new URL(url).hostname, url));
            }
            syncOptions();
            const option = [...select.options].find(item => item.value === url);
            if (option) option.selected = true;
            select.dispatchEvent(new Event('change'));
            urlInput.value = '';
        });
        urlInput.addEventListener('input', () => urlInput.setCustomValidity(''));
    }

    Object.entries(data.labels).forEach(([field, label]) => attachField(field, label));
    syncOptions();

    addButton.addEventListener('click', () => {
        const row = makeSourceRow();
        editor.append(row);
        row.querySelector('[name="source_label"]').focus();
    });
    editor.addEventListener('input', syncOptions);
    editor.addEventListener('click', event => {
        const remove = event.target.closest('.admin-source-remove');
        if (!remove) return;
        const rows = editor.querySelectorAll('.admin-source-row');
        if (rows.length > 1) remove.closest('.admin-source-row').remove();
        else remove.closest('.admin-source-row').querySelectorAll('input').forEach(input => {
            input.value = '';
        });
        syncOptions();
    });
})();
