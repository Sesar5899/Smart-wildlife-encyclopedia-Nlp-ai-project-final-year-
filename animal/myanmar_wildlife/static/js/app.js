const searchInput = document.getElementById('searchInput');
const searchSuggestions = document.getElementById('searchSuggestions');
const navMenuButton = document.getElementById('navMenuButton');
const navMenu = document.getElementById('navMenu');
let searchTimeout = null;
let searchRequestController = null;
let searchRequestId = 0;

if (navMenuButton && navMenu) {
    navMenuButton.addEventListener('click', () => {
        const open = navMenu.classList.toggle('open');
        navMenuButton.classList.toggle('open', open);
        navMenuButton.setAttribute('aria-expanded', String(open));
        document.body.classList.toggle('nav-open', open);
    });
    navMenu.querySelectorAll('a').forEach(link => link.addEventListener('click', () => {
        navMenu.classList.remove('open');
        navMenuButton.classList.remove('open');
        navMenuButton.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('nav-open');
    }));
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && navMenu.classList.contains('open')) navMenuButton.click();
    });
}

if (searchInput && searchSuggestions) {
    const setSuggestionsOpen = open => {
        searchSuggestions.classList.toggle('active', open);
        searchInput.setAttribute('aria-expanded', String(open));
    };

    document.addEventListener('keydown', event => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            searchInput.focus();
        }
    });
    searchInput.addEventListener('input', function() {
        clearTimeout(searchTimeout);
        searchRequestController?.abort();
        const requestId = ++searchRequestId;
        const query = this.value.trim();

        if (query.length < 2) {
            setSuggestionsOpen(false);
            searchSuggestions.replaceChildren();
            return;
        }

        searchTimeout = setTimeout(async () => {
            const controller = new AbortController();
            searchRequestController = controller;
            try {
                const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
                    signal: controller.signal,
                });
                if (!resp.ok) throw new Error(`Search failed with status ${resp.status}`);
                const results = await resp.json();
                if (!Array.isArray(results)) throw new Error('Search returned an invalid response');
                if (requestId !== searchRequestId) return;

                searchSuggestions.replaceChildren();
                if (results.length === 0) {
                    const empty = document.createElement('div');
                    empty.className = 'search-suggestion-item';
                    const label = document.createElement('span');
                    label.className = 'name-my';
                    label.textContent = 'ရလဒ် မတွေ့ပါ';
                    empty.append(label);
                    searchSuggestions.append(empty);
                } else {
                    results.forEach(animal => {
                        const item = document.createElement('a');
                        item.href = `/animal/${encodeURIComponent(String(animal.id))}`;
                        item.className = 'search-suggestion-item';
                        item.setAttribute('role', 'option');

                        const nameMy = document.createElement('div');
                        nameMy.className = 'name-my';
                        nameMy.textContent = animal.name_my || '';

                        const nameEn = document.createElement('div');
                        nameEn.className = 'name-en';
                        const scientificName = animal.scientific_name || '';
                        nameEn.textContent = scientificName
                            ? `${animal.name_en || ''} — ${scientificName}`
                            : animal.name_en || '';

                        item.append(nameMy, nameEn);
                        searchSuggestions.append(item);
                    });
                }
                setSuggestionsOpen(true);
            } catch (err) {
                if (err.name !== 'AbortError' && requestId === searchRequestId) {
                    setSuggestionsOpen(false);
                }
            }
        }, 300);
    });

    searchInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            const query = this.value.trim();
            if (query) {
                window.location.href = `/search?q=${encodeURIComponent(query)}`;
            }
        }
        if (e.key === 'Escape') {
            setSuggestionsOpen(false);
        }
    });

    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !searchSuggestions.contains(e.target)) {
            setSuggestionsOpen(false);
        }
    });
}

[
    ['ecosystemSearchInput', 'ecosystemSearchSuggestions', '/api/ecosystems/search'],
    ['protectedAreaSearchInput', 'protectedAreaSearchSuggestions', '/api/protected-areas/search'],
].forEach(([inputId, suggestionsId, endpoint]) => {
    const ecosystemSearchInput = document.getElementById(inputId);
    const ecosystemSuggestions = document.getElementById(suggestionsId);
    if (!ecosystemSearchInput || !ecosystemSuggestions) return;
    let timeout = null;
    let controller = null;
    let requestId = 0;
    const setOpen = open => {
        ecosystemSuggestions.classList.toggle('active', open);
        ecosystemSearchInput.setAttribute('aria-expanded', String(open));
    };

    ecosystemSearchInput.addEventListener('input', () => {
        clearTimeout(timeout);
        controller?.abort();
        const currentId = ++requestId;
        const query = ecosystemSearchInput.value.trim();
        if (query.length < 2) {
            ecosystemSuggestions.replaceChildren();
            setOpen(false);
            return;
        }

        timeout = setTimeout(async () => {
            controller = new AbortController();
            try {
                const response = await fetch(
                    `${endpoint}?q=${encodeURIComponent(query)}`,
                    {signal: controller.signal}
                );
                if (!response.ok) throw new Error(`Search failed with status ${response.status}`);
                const results = await response.json();
                if (!Array.isArray(results) || currentId !== requestId) return;
                ecosystemSuggestions.replaceChildren();
                if (results.length === 0) {
                    const empty = document.createElement('div');
                    empty.className = 'search-suggestion-item';
                    empty.textContent = 'ရလဒ် မတွေ့ပါ';
                    ecosystemSuggestions.append(empty);
                } else {
                    results.forEach(ecosystem => {
                        const item = document.createElement('a');
                        item.href = ecosystem.url;
                        item.className = 'search-suggestion-item';
                        item.setAttribute('role', 'option');
                        const nameMy = document.createElement('div');
                        nameMy.className = 'name-my';
                        nameMy.textContent = ecosystem.name_mm || ecosystem.name;
                        const nameEn = document.createElement('div');
                        nameEn.className = 'name-en';
                        nameEn.textContent = ecosystem.name_mm ? ecosystem.name : '';
                        item.append(nameMy, nameEn);
                        ecosystemSuggestions.append(item);
                    });
                }
                setOpen(true);
            } catch (error) {
                if (error.name !== 'AbortError' && currentId === requestId) setOpen(false);
            }
        }, 300);
    });

    ecosystemSearchInput.addEventListener('keydown', event => {
        if (event.key === 'Escape') setOpen(false);
    });
    document.addEventListener('click', event => {
        if (!ecosystemSearchInput.contains(event.target)
            && !ecosystemSuggestions.contains(event.target)) setOpen(false);
    });
});

const studioSearchInput = document.getElementById('studioSearchInput');
const studioSuggestions = document.getElementById('studioSearchSuggestions');
if (studioSearchInput && studioSuggestions) {
    const section = studioSearchInput.form.dataset.studioSection;
    let timeout = null;
    let controller = null;
    let requestId = 0;
    const setOpen = open => {
        studioSuggestions.classList.toggle('active', open);
        studioSearchInput.setAttribute('aria-expanded', String(open));
    };

    studioSearchInput.addEventListener('input', () => {
        clearTimeout(timeout);
        controller?.abort();
        const currentId = ++requestId;
        const query = studioSearchInput.value.trim();
        if (query.length < 2) {
            studioSuggestions.replaceChildren();
            setOpen(false);
            return;
        }

        timeout = setTimeout(async () => {
            controller = new AbortController();
            try {
                const response = await fetch(
                    `/admin/api/search?section=${encodeURIComponent(section)}&q=${encodeURIComponent(query)}`,
                    {signal: controller.signal}
                );
                if (!response.ok) throw new Error(`Search failed with status ${response.status}`);
                const results = await response.json();
                if (!Array.isArray(results) || currentId !== requestId) return;
                studioSuggestions.replaceChildren();
                if (results.length === 0) {
                    const empty = document.createElement('div');
                    empty.className = 'search-suggestion-item';
                    empty.textContent = 'ရလဒ် မတွေ့ပါ';
                    studioSuggestions.append(empty);
                } else {
                    results.forEach(result => {
                        const item = document.createElement('a');
                        item.href = result.url;
                        item.className = 'search-suggestion-item';
                        item.setAttribute('role', 'option');
                        const label = document.createElement('div');
                        label.className = 'name-my';
                        label.textContent = result.label || '';
                        const subtitle = document.createElement('div');
                        subtitle.className = 'name-en';
                        subtitle.textContent = result.subtitle || '';
                        item.append(label, subtitle);
                        studioSuggestions.append(item);
                    });
                }
                setOpen(true);
            } catch (error) {
                if (error.name !== 'AbortError' && currentId === requestId) setOpen(false);
            }
        }, 300);
    });

    studioSearchInput.addEventListener('keydown', event => {
        if (event.key === 'Escape') setOpen(false);
    });
    document.addEventListener('click', event => {
        if (!studioSearchInput.contains(event.target)
            && !studioSuggestions.contains(event.target)) setOpen(false);
    });
}

document.querySelectorAll('[data-catalog-auto-filter]').forEach(form => {
    const queryInput = form.querySelector('[data-auto-filter-query]');
    const profileElement = form.querySelector('[data-auto-filter-profiles]');
    const selects = [...form.querySelectorAll('[data-auto-filter-field]')];
    if (!queryInput || !profileElement || selects.length === 0) return;

    let profiles;
    try {
        profiles = JSON.parse(profileElement.textContent);
    } catch {
        return;
    }
    if (!Array.isArray(profiles)) return;

    const normalize = value => String(value || '')
        .normalize('NFKC')
        .toLocaleLowerCase()
        .replace(/[\u200B-\u200D\uFEFF]/g, '')
        .replace(/[_\-–—/၊,.;:()]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    const normalizedProfiles = profiles.map(profile => ({
        profile,
        names: (profile.names || []).map(normalize).filter(Boolean),
    }));

    const clearAutomaticSelections = () => {
        selects.forEach(select => {
            [...select.options].forEach(option => {
                option.disabled = false;
                option.hidden = false;
            });
            if (select.dataset.autoSelected === 'true') select.value = '';
            delete select.dataset.autoSelected;
            select.classList.remove('is-auto-selected');
        });
    };

    const setAutomaticSelection = (select, value) => {
        select.value = value;
        select.dataset.autoSelected = 'true';
        select.classList.toggle('is-auto-selected', Boolean(value));
        [...select.options].forEach(option => {
            const unavailable = option.value !== value;
            option.disabled = unavailable;
            option.hidden = unavailable;
        });
    };

    const matchingOption = (select, query) => {
        const options = [...select.options]
            .filter(option => option.value)
            .map(option => ({
                option,
                aliases: [normalize(option.value), normalize(option.textContent)]
                    .filter(Boolean),
            }));
        const exact = options.filter(item =>
            item.aliases.some(alias => alias === query)
        );
        if (exact.length === 1) return exact[0].option;

        const contained = options.filter(item =>
            item.aliases.some(alias => alias.length >= 3 && query.includes(alias))
        );
        if (contained.length === 1) return contained[0].option;

        if (query.length < 3) return null;
        const partial = options.filter(item =>
            item.aliases.some(alias => alias.includes(query))
        );
        return partial.length === 1 ? partial[0].option : null;
    };

    const autoSelectFilters = () => {
        const query = normalize(queryInput.value);
        clearAutomaticSelections();
        if (query.length < 2) {
            return;
        }

        const matches = normalizedProfiles.filter(item =>
            item.names.some(name => name.includes(query))
        );
        const exactMatches = matches.filter(item => item.names.includes(query));
        const match = exactMatches.length === 1
            ? exactMatches[0]
            : matches.length === 1 ? matches[0] : null;
        if (!match) {
            selects.forEach(select => {
                const option = matchingOption(select, query);
                if (!option) return;
                setAutomaticSelection(select, option.value);
            });
            return;
        }

        selects.forEach(select => {
            const field = select.dataset.autoFilterField;
            const value = String(match.profile[field] || '');
            const hasOption = [...select.options].some(option => option.value === value);
            setAutomaticSelection(select, hasOption ? value : '');
        });
    };

    selects.forEach(select => select.addEventListener('change', () => {
        if (select.dataset.autoSelected === 'true') return;
        delete select.dataset.autoSelected;
        select.classList.remove('is-auto-selected');
    }));
    queryInput.addEventListener('input', autoSelectFilters);
    autoSelectFilters();
});
