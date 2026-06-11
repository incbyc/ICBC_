
            function buildStaffFromLegacy(site) {
                var staff = site.staff ? site.staff.slice() : [];
                if (!staff.length) {
                    if (site.pastor && site.pastor.name) {
                        staff.push({
                            full_name: site.pastor.name,
                            role: 'Pastor',
                            description: site.pastor.description || '',
                            year_joined: site.pastor.year_joined || null,
                            photo: site.pastor.photo
                        });
                    }
                    (site.teachers || []).forEach(function (t) {
                        staff.push({
                            full_name: t.name,
                            role: 'Teacher',
                            description: t.description || '',
                            year_joined: t.year_joined || null,
                            photo: t.photo,
                            sort_order: t.sort_order || 0
                        });
                    });
                    (site.care_team || []).forEach(function (c) {
                        staff.push({
                            full_name: c.name,
                            role: 'Compassionate Care',
                            description: c.description || '',
                            year_joined: c.year_joined || null,
                            photo: c.photo,
                            sort_order: c.sort_order || 0
                        });
                    });
                }
                return staff;
            }

            function staffPhotoUrl(person) {
                if (person.photo) return person.photo;
                if (person.photo_url) return person.photo_url;
                return null;
            }

            function renderStaffCard(person) {
                var img = staffPhotoUrl(person);
                var imgHtml = img
                    ? '<img class="team-photo" src="' + img + '" alt="">'
                    : '<div class="team-photo"></div>';
                var year = person.year_joined
                    ? '<p class="team-meta">Joined ' + person.year_joined + '</p>'
                    : '';
                var desc = person.description
                    ? '<p class="team-desc">' + person.description + '</p>'
                    : '';
                return (
                    '<div class="team-card team-card-wide">' +
                    '<div class="team-head">' + imgHtml +
                    '<div><div class="team-name">' + person.full_name + '</div>' +
                    '<div class="team-role">' + (person.role || 'Staff') + '</div>' +
                    year + '</div></div>' + desc + '</div>'
                );
            }

            function renderMinistryTeam(site) {
                var staff = buildStaffFromLegacy(site);
                var count = site.staff_count != null ? site.staff_count : staff.length;
                var countNote = document.getElementById('staff-count-note');
                if (countNote) {
                    countNote.textContent = count
                        ? count + ' staff member' + (count === 1 ? '' : 's') + ' at this ICBC'
                        : '';
                }

                var pastorShell = document.getElementById('pastor-shell');
                pastorShell.innerHTML = '';
                var pastor = null;
                staff.forEach(function (p) {
                    if (p.role === 'Pastor') pastor = p;
                });
                if (!pastor && site.pastor && site.pastor.name) {
                    pastor = {
                        full_name: site.pastor.name,
                        description: site.pastor.description || '',
                        photo: site.pastor.photo
                    };
                }
                if (pastor && pastor.full_name) {
                    var pImg = staffPhotoUrl(pastor);
                    if (pImg) {
                        pastorShell.innerHTML += '<img class="pastor-photo" src="' + pImg + '" alt="">';
                    }
                    pastorShell.innerHTML += '<div><div class="pastor-name">' + pastor.full_name + '</div>';
                    if (pastor.description) {
                        pastorShell.innerHTML += '<p class="team-desc">' + pastor.description + '</p>';
                    }
                    pastorShell.innerHTML += '</div>';
                } else {
                    pastorShell.innerHTML = '<p class="muted-note">Add a pastor in Supabase (staff table, role Pastor).</p>';
                }

                var shell = document.getElementById('staff-sections-shell');
                shell.innerHTML = '';
                [
                    { title: 'Teachers', role: 'Teacher' },
                    { title: 'Compassionate care team', role: 'Compassionate Care' },
                    { title: 'Other staff', role: 'Other' }
                ].forEach(function (g) {
                    var people = staff.filter(function (p) { return p.role === g.role; });
                    if (!people.length) return;
                    var html = '<div class="section"><div class="section-title">' + g.title + '</div><div class="team-grid">';
                    people.forEach(function (p) { html += renderStaffCard(p); });
                    html += '</div></div>';
                    shell.innerHTML += html;
                });
                if (!shell.innerHTML) {
                    shell.innerHTML = '<p class="muted-note">Add teachers and care team in Supabase (staff table).</p>';
                }
            }
