(function (global) {
    'use strict';

    var RADIUS_M = 7000;
    var SEGMENTS = 20;
    var EARTH_RADIUS_M = 6378137;

    function toRad(degrees) {
        return degrees * Math.PI / 180;
    }

    function toDeg(radians) {
        return radians * 180 / Math.PI;
    }

    function destinationPoint(lat, lon, bearingDeg, distanceM) {
        var lat1 = toRad(lat);
        var lon1 = toRad(lon);
        var bearing = toRad(bearingDeg);
        var angularDistance = distanceM / EARTH_RADIUS_M;

        var lat2 = Math.asin(
            Math.sin(lat1) * Math.cos(angularDistance)
            + Math.cos(lat1) * Math.sin(angularDistance) * Math.cos(bearing)
        );
        var lon2 = lon1 + Math.atan2(
            Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(lat1),
            Math.cos(angularDistance) - Math.sin(lat1) * Math.sin(lat2)
        );

        return { lat: toDeg(lat2), lon: toDeg(lon2) };
    }

    function buildCatchmentRing(lat, lon) {
        var ring = [];
        var index;

        for (index = 0; index < SEGMENTS; index += 1) {
            var bearing = (360 / SEGMENTS) * index;
            var point = destinationPoint(lat, lon, bearing, RADIUS_M);
            ring.push([point.lon, point.lat]);
        }
        ring.push([ring[0][0], ring[0][1]]);
        return ring;
    }

    function buildCatchmentFeature(siteName, lat, lng, extraProps) {
        var properties = {
            'Site Name': siteName || '',
            Latitude: lat,
            Longitude: lng
        };

        if (extraProps) {
            Object.keys(extraProps).forEach(function (key) {
                properties[key] = extraProps[key];
            });
        }

        return {
            type: 'Feature',
            properties: properties,
            geometry: {
                type: 'MultiPolygon',
                coordinates: [[buildCatchmentRing(lat, lng)]]
            }
        };
    }

    function normaliseSiteKey(name) {
        if (!name) return '';
        return String(name).trim().toLowerCase().replace(/\s+/g, ' ');
    }

    function haversineMeters(lat1, lon1, lat2, lon2) {
        var latA = toRad(lat1);
        var latB = toRad(lat2);
        var dLat = toRad(lat2 - lat1);
        var dLon = toRad(lon2 - lon1);
        var a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
            + Math.cos(latA) * Math.cos(latB) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)));
    }

    function catchmentRadiiFromSite(lat, lon, ring) {
        var points = ring.length > 1 && ring[0][0] === ring[ring.length - 1][0]
            && ring[0][1] === ring[ring.length - 1][1]
            ? ring.slice(0, -1)
            : ring;
        return points.map(function (point) {
            return haversineMeters(lat, lon, point[1], point[0]);
        });
    }

    function catchmentIsAligned(lat, lon, ring, toleranceM) {
        var radii = catchmentRadiiFromSite(lat, lon, ring);
        if (!radii.length) return false;
        var tolerance = typeof toleranceM === 'number' ? toleranceM : 75;
        return radii.every(function (radius) {
            return Math.abs(radius - RADIUS_M) <= tolerance;
        });
    }

    function findCatchmentFeatureByName(features, siteName) {
        var target = normaliseSiteKey(siteName);
        if (!target || !features || !features.length) return null;
        for (var index = 0; index < features.length; index += 1) {
            var feature = features[index];
            var candidate = normaliseSiteKey(
                feature && feature.properties ? feature.properties['Site Name'] : ''
            );
            if (candidate === target) return feature;
        }
        return null;
    }

    global.IcbcCatchment = {
        RADIUS_M: RADIUS_M,
        SEGMENTS: SEGMENTS,
        buildCatchmentRing: buildCatchmentRing,
        buildCatchmentFeature: buildCatchmentFeature,
        normaliseSiteKey: normaliseSiteKey,
        haversineMeters: haversineMeters,
        catchmentRadiiFromSite: catchmentRadiiFromSite,
        catchmentIsAligned: catchmentIsAligned,
        findCatchmentFeatureByName: findCatchmentFeatureByName
    };
}(typeof window !== 'undefined' ? window : this));
