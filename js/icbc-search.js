var mapSearchIndex = [];
var icbcSiteRegistry = {};
var ICBC_RAINFALL_BY_SITE = {};
var ICBC_PASTOR_FAMILY_BY_SITE = {};
var ICBC_SITE_PROFILES_BY_SLUG = {};
var ICBC_AVG_HOME_VISITS_BY_SLUG = {};
var ICBC_WEEKLY_METRICS_BY_SLUG = {};

function initSiteProfilesFromSeed() {
    if (typeof window !== 'undefined' && window.ICBC_SITE_PROFILES_SEED) {
        ICBC_SITE_PROFILES_BY_SLUG = Object.assign({}, window.ICBC_SITE_PROFILES_SEED);
    }
}

function initWeeklyMetricsFromSeed() {
    if (typeof window === 'undefined' || !window.ICBC_WEEKLY_METRICS_SEED) return;

    ICBC_WEEKLY_METRICS_BY_SLUG = {};
    ICBC_AVG_HOME_VISITS_BY_SLUG = {};
    Object.keys(window.ICBC_WEEKLY_METRICS_SEED).forEach(function (slug) {
        var row = window.ICBC_WEEKLY_METRICS_SEED[slug] || {};
        ICBC_WEEKLY_METRICS_BY_SLUG[slug] = {
            avg_men: Number(row.avg_men),
            avg_women: Number(row.avg_women),
            avg_youth: Number(row.avg_youth),
            avg_children: Number(row.avg_children),
            weeks_recorded: Number(row.weeks_recorded) || 0
        };
        var avgHv = Number(row.avg_home_visits_per_week);
        if (!isNaN(avgHv) && avgHv >= 5) {
            ICBC_AVG_HOME_VISITS_BY_SLUG[slug] = avgHv;
        }
    });
}

function resolveSeedDataUrl(relativePath) {
    var value = String(relativePath || '').replace(/^\//, '');
    if (typeof window === 'undefined' || !window.location) return value;
    if (window.location.protocol !== 'http:' && window.location.protocol !== 'https:') {
        return value;
    }
    var path = window.location.pathname || '/';
    var base = '/';
    if (/\/index\.html$/i.test(path)) {
        base = path.replace(/\/index\.html$/i, '/');
    } else if (path.charAt(path.length - 1) !== '/') {
        var lastSegment = path.split('/').pop() || '';
        if (/\.[a-z0-9]+$/i.test(lastSegment)) {
            var lastSlash = path.lastIndexOf('/');
            base = lastSlash >= 0 ? path.slice(0, lastSlash + 1) : '/';
        } else {
            base = path + '/';
        }
    } else {
        base = path;
    }
    if (value.charAt(0) === '/') {
        if (base === '/' || base === '') return value;
        return base.replace(/\/$/, '') + value;
    }
    return base + value;
}

initSiteProfilesFromSeed();

function searchEscapeHtml(str) {
    if (str == null || str === '') return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function normalizeSearchText(value) {
    return String(value || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .trim();
}

function parseCsvRows(text) {
    var rows = [];
    var row = [];
    var cell = '';
    var inQuotes = false;
    var i;
    var ch;

    for (i = 0; i < text.length; i++) {
        ch = text[i];
        if (ch === '"') {
            if (inQuotes && text[i + 1] === '"') {
                cell += '"';
                i++;
            } else {
                inQuotes = !inQuotes;
            }
            continue;
        }
        if (ch === ',' && !inQuotes) {
            row.push(cell);
            cell = '';
            continue;
        }
        if ((ch === '\n' || ch === '\r') && !inQuotes) {
            if (ch === '\r' && text[i + 1] === '\n') i++;
            if (cell.length || row.length) {
                row.push(cell);
                rows.push(row);
            }
            row = [];
            cell = '';
            continue;
        }
        cell += ch;
    }
    if (cell.length || row.length) {
        row.push(cell);
        rows.push(row);
    }
    return rows;
}

function registerIcbcSiteMarker(layer, props) {
    var siteName = props['Site Name'] || '';
    var slugFn = window.slugifyForApi || function (t) {
        return String(t || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '-');
    };
    var slug = (props._slug && String(props._slug).trim().toLowerCase()) || slugFn(siteName);
    var entry = {
        siteName: siteName,
        siteSlug: slug,
        region: props.Region || '',
        pastor: props.Pastor || '',
        props: props,
        layer: layer,
        latlng: layer.getLatLng()
    };

    icbcSiteRegistry[slug] = entry;

    mapSearchIndex.push({
        id: 'site:' + slug,
        title: siteName,
        meta: props.Region ? props.Region + ' · ICBC site' : 'ICBC site',
        searchText: normalizeSearchText(siteName + ' ' + slug + ' ' + (props.Region || '')),
        entry: entry
    });

    if (props.Pastor) {
        mapSearchIndex.push({
            id: 'pastor:' + slug,
            title: props.Pastor,
            meta: siteName + ' · Pastor',
            searchText: normalizeSearchText(props.Pastor + ' ' + siteName + ' pastor'),
            entry: entry
        });
    }
}

function registerPastorFamilyRow(row) {
    var slug = (row.site_slug || '').trim().toLowerCase();
    var role = (row.role || '').trim();
    if (!slug || role !== 'Pastor') return;
    ICBC_PASTOR_FAMILY_BY_SITE[slug] = {
        spouse_name: (row.spouse_name || '').trim(),
        children_count: row.children_count != null && row.children_count !== ''
            ? row.children_count
            : ''
    };
}

function registerStaffRow(row) {
    var slug = (row.site_slug || '').trim().toLowerCase();
    var fullName = (row.full_name || '').trim();
    var role = (row.role || '').trim();
    if (!slug || !fullName || role !== 'Pastor') return;

    var site = icbcSiteRegistry[slug];
    if (!site) return;

    if (role === 'Pastor' && site.pastor &&
        normalizeSearchText(fullName) === normalizeSearchText(site.pastor)) {
        return;
    }

    var id = 'staff:' + slug + ':' + normalizeSearchText(fullName) + ':' + normalizeSearchText(role);
    var exists = false;
    var i;
    for (i = 0; i < mapSearchIndex.length; i++) {
        if (mapSearchIndex[i].id === id) {
            exists = true;
            break;
        }
    }
    if (exists) return;

    mapSearchIndex.push({
        id: id,
        title: fullName,
        meta: (site.siteName || slug) + ' · ' + (role || 'Staff'),
        searchText: normalizeSearchText(fullName + ' ' + role + ' ' + site.siteName + ' staff'),
        entry: site
    });
}

function searchMapIndex(query, limit) {
    var q = normalizeSearchText(query);
    if (!q) return [];
    var matches = [];
    var i;
    for (i = 0; i < mapSearchIndex.length; i++) {
        if (mapSearchIndex[i].searchText.indexOf(q) !== -1) {
            matches.push(mapSearchIndex[i]);
        }
    }
    matches.sort(function (a, b) {
        var aStarts = normalizeSearchText(a.title).indexOf(q) === 0 ? 0 : 1;
        var bStarts = normalizeSearchText(b.title).indexOf(q) === 0 ? 0 : 1;
        if (aStarts !== bStarts) return aStarts - bStarts;
        return a.title.localeCompare(b.title);
    });
    return matches.slice(0, limit || 8);
}

function focusSearchEntry(entry) {
    if (!entry || !entry.layer) return;
    if (typeof window.openSiteSidebar === 'function') {
        window.openSiteSidebar('icbc', entry.props, entry.layer);
    }
    if (typeof window.scheduleFlyToMarker === 'function') {
        window.scheduleFlyToMarker(entry.layer);
    } else if (typeof map !== 'undefined' && entry.latlng) {
        map.flyTo(entry.latlng, Math.max(map.getZoom(), 12), { duration: 0.8 });
    }
}

function loadStaffSearchIndex() {
    fetch('supabase/seed/staff.csv')
        .then(function (res) {
            if (!res.ok) throw new Error('staff.csv not found');
            return res.text();
        })
        .then(function (text) {
            var rows = parseCsvRows(text);
            if (rows.length < 2) return;
            var headers = rows[0];
            var hi = {};
            var c;
            for (c = 0; c < headers.length; c++) {
                hi[headers[c].trim()] = c;
            }
            var r;
            for (r = 1; r < rows.length; r++) {
                var cells = rows[r];
                registerStaffRow({
                    site_slug: cells[hi.site_slug],
                    full_name: cells[hi.full_name],
                    role: cells[hi.role]
                });
                registerPastorFamilyRow({
                    site_slug: cells[hi.site_slug],
                    role: cells[hi.role],
                    spouse_name: hi.spouse_name != null ? cells[hi.spouse_name] : '',
                    children_count: hi.children_count != null ? cells[hi.children_count] : ''
                });
            }
        })
        .catch(function () {
            /* staff search optional when opened via file:// */
        });
}

function loadSiteProfilesSeed() {
    return fetch(resolveSeedDataUrl('supabase/seed/icbc_site_profiles.csv'))
        .then(function (res) {
            if (!res.ok) throw new Error('icbc_site_profiles.csv not found');
            return res.text();
        })
        .then(function (text) {
            var rows = parseCsvRows(text);
            if (rows.length < 2) return;
            var headers = rows[0];
            var hi = {};
            var c;
            for (c = 0; c < headers.length; c++) {
                hi[headers[c].trim()] = c;
            }
            ICBC_SITE_PROFILES_BY_SLUG = {};
            var r;
            for (r = 1; r < rows.length; r++) {
                var cells = rows[r];
                var slug = String(cells[hi.site_slug] || '').trim().toLowerCase();
                if (!slug) continue;
                ICBC_SITE_PROFILES_BY_SLUG[slug] = {
                    compassionate_care_members: Number(cells[hi.compassionate_care_members]) || 0
                };
            }
        })
        .catch(function () {
            initSiteProfilesFromSeed();
        });
}

function loadSiteWeeklyMetricsSeed() {
    initWeeklyMetricsFromSeed();
    return fetch(resolveSeedDataUrl('supabase/seed/site_weekly_metrics.csv'))
        .then(function (res) {
            if (!res.ok) throw new Error('site_weekly_metrics.csv not found');
            return res.text();
        })
        .then(function (text) {
            var rows = parseCsvRows(text);
            if (rows.length < 2) return;
            var headers = rows[0];
            var hi = {};
            var c;
            for (c = 0; c < headers.length; c++) {
                hi[headers[c].trim()] = c;
            }
            ICBC_AVG_HOME_VISITS_BY_SLUG = {};
            ICBC_WEEKLY_METRICS_BY_SLUG = {};
            var r;
            for (r = 1; r < rows.length; r++) {
                var cells = rows[r];
                var slug = String(cells[hi.site_slug] || '').trim().toLowerCase();
                if (!slug) continue;
                var metrics = {
                    avg_men: Number(cells[hi.avg_men]),
                    avg_women: Number(cells[hi.avg_women]),
                    avg_youth: Number(cells[hi.avg_youth]),
                    avg_children: Number(cells[hi.avg_children]),
                    weeks_recorded: Number(cells[hi.weeks_recorded]) || 0
                };
                ICBC_WEEKLY_METRICS_BY_SLUG[slug] = metrics;
                var avgHv = Number(cells[hi.avg_home_visits_per_week]);
                if (!isNaN(avgHv) && avgHv >= 5) {
                    ICBC_AVG_HOME_VISITS_BY_SLUG[slug] = avgHv;
                }
            }
        })
        .catch(function () {
            initWeeklyMetricsFromSeed();
        });
}

function loadRainfallSeed() {
    return fetch('supabase/seed/rainfall_monthly.csv')
        .then(function (res) {
            if (!res.ok) throw new Error('rainfall_monthly.csv not found');
            return res.text();
        })
        .then(function (text) {
            var rows = parseCsvRows(text);
            if (rows.length < 2) return;
            var headers = rows[0];
            var hi = {};
            var c;
            for (c = 0; c < headers.length; c++) {
                hi[headers[c].trim()] = c;
            }
            ICBC_RAINFALL_BY_SITE = {};
            var r;
            for (r = 1; r < rows.length; r++) {
                var cells = rows[r];
                var slug = String(cells[hi.site_slug] || '').trim().toLowerCase();
                if (!slug) continue;
                if (!ICBC_RAINFALL_BY_SITE[slug]) ICBC_RAINFALL_BY_SITE[slug] = [];
                ICBC_RAINFALL_BY_SITE[slug].push({
                    month: Number(cells[hi.month]) || 0,
                    month_label: cells[hi.month_label] || '',
                    rainfall_mm: Number(cells[hi.rainfall_mm]) || 0,
                    temperature_c: cells[hi.temperature_c] !== '' && cells[hi.temperature_c] != null
                        ? Number(cells[hi.temperature_c]) : null
                });
            }
            Object.keys(ICBC_RAINFALL_BY_SITE).forEach(function (slug) {
                ICBC_RAINFALL_BY_SITE[slug].sort(function (a, b) {
                    return a.month - b.month;
                });
            });
        })
        .catch(function () {
            /* rainfall chart optional when opened via file:// */
        });
}

function initMapSearchControl(host) {
    if (!host) {
        host = document.getElementById('mapSearchHost');
    }
    if (!host || host.dataset.searchInit === '1') return;
    host.dataset.searchInit = '1';

    host.innerHTML =
        '<div class="map-search-control">' +
        '<div class="map-search-inner">' +
        '<i class="fas fa-search map-search-input-icon" aria-hidden="true"></i>' +
        '<input type="search" class="map-search-input" id="mapSearchInput" ' +
        'placeholder="Search" autocomplete="off" aria-label="Search map">' +
        '</div>' +
        '<div class="map-search-results is-hidden" id="mapSearchResults"></div>' +
        '</div>';

    var input = host.querySelector('#mapSearchInput');
    var resultsEl = host.querySelector('#mapSearchResults');

    function renderResults(items) {
        if (!items.length) {
            resultsEl.innerHTML = '<div class="map-search-empty">No matches</div>';
            resultsEl.classList.remove('is-hidden');
            return;
        }
        var html = '';
        items.forEach(function (item) {
            html += '<button type="button" class="map-search-item" data-id="' + item.id + '">' +
                '<div class="map-search-item-title">' + searchEscapeHtml(item.title) + '</div>' +
                '<div class="map-search-item-meta">' + searchEscapeHtml(item.meta) + '</div>' +
                '</button>';
        });
        resultsEl.innerHTML = html;
        resultsEl.classList.remove('is-hidden');
    }

    function hideResults() {
        resultsEl.classList.add('is-hidden');
        resultsEl.innerHTML = '';
    }

    input.addEventListener('input', function () {
        var q = input.value.trim();
        if (q.length < 2) {
            hideResults();
            return;
        }
        renderResults(searchMapIndex(q, 8));
    });

    input.addEventListener('focus', function () {
        if (input.value.trim().length >= 2) {
            renderResults(searchMapIndex(input.value.trim(), 8));
        }
    });

    resultsEl.addEventListener('mousedown', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var btn = e.target.closest('.map-search-item');
        if (!btn) return;
        var id = btn.getAttribute('data-id');
        var match = null;
        var i;
        for (i = 0; i < mapSearchIndex.length; i++) {
            if (mapSearchIndex[i].id === id) {
                match = mapSearchIndex[i];
                break;
            }
        }
        if (match) {
            focusSearchEntry(match.entry);
            hideResults();
            input.value = '';
            input.blur();
        }
    });

    document.addEventListener('click', function (e) {
        if (!host.contains(e.target)) {
            hideResults();
        }
    });

    input.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            hideResults();
            input.blur();
        }
    });

    if (typeof L !== 'undefined' && L.DomEvent) {
        L.DomEvent.disableClickPropagation(host);
        L.DomEvent.disableScrollPropagation(host);
    }
}
