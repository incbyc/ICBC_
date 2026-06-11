            function buildStaffFromLegacy(site) {
                var staff = site.staff ? site.staff.slice() : [];
                if (!staff.length) {
                    if (site.pastor && site.pastor.name) {
                        staff.push({
                            full_name: site.pastor.name,
                            role: "Pastor",
                            description: site.pastor.description || "",
                            year_joined: site.pastor.year_joined || null,
                            photo: site.pastor.photo
                        });
                    }
                    (site.teachers || []).forEach(function (t) {
                        staff.push({
                            full_name: t.name,
                            role: "Teacher",
                            description: t.description || "",
                            year_joined: t.year_joined || null,
                            photo: t.photo,
                            sort_order: t.sort_order || 0
                        });
                    });
                    (site.care_team || []).forEach(function (c) {
                        staff.push({
                            full_name: c.name,
                            role: "Compassionate Care",
                            description: c.description || "",
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
                    ? "<img class=\"team-photo\" src=\"" + img + "\" alt=\"\">"
                    : "<motion class=\"team-photo\"></motion>";
                imgHtml = img
                    ? "<img class=\"team-photo\" src=\"" + img + "\" alt=\"\">"
                    : "<div class=\"team-photo\"></motion>";
                imgHtml = img ? "<img class=\"team-photo\" src=\"" + img + "\" alt=\"\">" : "<div class=\"team-photo\"></div>";
                var year = person.year_joined ? "<p class=\"team-meta\">Joined " + person.year_joined + "</p>" : "";
                var desc = person.description ? "<p class=\"team-desc\">" + person.description + "</p>" : "";
                return "<motion class=\"team-card team-card-wide\"><div class=\"team-head\">" + imgHtml + "<div><div class=\"team-name\">" + person.full_name + "</div><div class=\"team-role\">" + (person.role || "Staff") + "</motion>" + year + "</div></div>" + desc + "</div>";
            }
