var hideLabel = function (label) {
    label.labelObject.style.opacity = 0;
    label.labelObject.style.transition = 'opacity 0s';
};
var showLabel = function (label) {
    label.labelObject.style.opacity = 1;
    label.labelObject.style.transition = 'opacity 0.15s';
};

labelEngine = new labelgun.default(hideLabel, showLabel);

var labels = [];
var totalMarkers = 0;
var ICBC_LABEL_FULL_ZOOM = 9;

function getTooltipContainer(layer) {
    if (!layer.getTooltip) return null;
    var tip = layer.getTooltip();
    if (!tip) return null;
    if (layer.isTooltipOpen && !layer.isTooltipOpen()) {
        layer.openTooltip();
    }
    if (tip._source && tip._source._tooltip && tip._source._tooltip._container) {
        return tip._source._tooltip._container;
    }
    if (tip.getElement) {
        return tip.getElement();
    }
    return null;
}

function isIcbcSiteLabelLayer(layer) {
    var label = getTooltipContainer(layer);
    return !!(label && label.classList && label.classList.contains('css_ICBCSites_6'));
}

function labelWeightForLayer(layer) {
    var label = getTooltipContainer(layer);
    if (!label || !label.classList) return 4;
    if (label.classList.contains('css_ICBCSites_6')) return 10;
    if (label.classList.contains('css_CMS_5')) return 6;
    if (label.classList.contains('css_Roads_4')) return 2;
    return 4;
}

function tooltipBoundsInMapCoords(labelEl, layer) {
    var mapEl = map.getContainer();
    var mapRect = mapEl.getBoundingClientRect();
    var rect = labelEl.getBoundingClientRect();
    var bottomLeft;
    var topRight;

    if (rect.width > 0 && rect.height > 0) {
        var x1 = rect.left - mapRect.left;
        var y1 = rect.top - mapRect.top;
        var x2 = rect.right - mapRect.left;
        var y2 = rect.bottom - mapRect.top;
        bottomLeft = map.containerPointToLatLng([x1, y2]);
        topRight = map.containerPointToLatLng([x2, y1]);
        return {
            bottomLeft: [bottomLeft.lng, bottomLeft.lat],
            topRight: [topRight.lng, topRight.lat]
        };
    }

    if (!layer.getLatLng) return null;
    var pt = map.latLngToContainerPoint(layer.getLatLng());
    bottomLeft = map.containerPointToLatLng([pt.x - 50, pt.y + 4]);
    topRight = map.containerPointToLatLng([pt.x + 50, pt.y - 32]);
    return {
        bottomLeft: [bottomLeft.lng, bottomLeft.lat],
        topRight: [topRight.lng, topRight.lat]
    };
}

function ingestLayerLabel(layer, id, engine) {
    var label = getTooltipContainer(layer);
    if (!label) return;

    var boundingBox = tooltipBoundsInMapCoords(label, layer);
    if (!boundingBox) return;

    engine.ingestLabel(
        boundingBox,
        id,
        labelWeightForLayer(layer),
        label,
        'label-' + id,
        false
    );

    if (!layer.added) {
        layer.addTo(map);
        layer.added = true;
    }
}

function revealIcbcLabelsInViewport(icbcGroups) {
    if (!map || map.getZoom() < ICBC_LABEL_FULL_ZOOM) return;

    var bounds = map.getBounds().pad(0.08);
    (icbcGroups || []).forEach(function (group) {
        if (!group || !group.eachLayer) return;
        group.eachLayer(function (layer) {
            if (!isIcbcSiteLabelLayer(layer)) return;
            var ll = layer.getLatLng ? layer.getLatLng() : null;
            if (!ll || !bounds.contains(ll)) return;
            var label = getTooltipContainer(layer);
            if (!label) return;
            label.style.display = 'block';
            label.style.visibility = 'visible';
            label.style.opacity = 1;
            label.style.transition = 'opacity 0.15s';
        });
    });
}

function resetLabels(markerGroups, icbcRevealGroups) {
    var i = 0;
    var j;

    labelEngine.reset();
    for (j = 0; j < markerGroups.length; j++) {
        if (!markerGroups[j]) continue;
        markerGroups[j].eachLayer(function (layer) {
            ingestLayerLabel(layer, ++i, labelEngine);
        });
    }
    labelEngine.update();
    revealIcbcLabelsInViewport(icbcRevealGroups);
}

function addLabel(layer, id) {
    ingestLayerLabel(layer, id, labelEngine);
}
