'use client';

import { useEffect, useRef } from 'react';
import L from 'leaflet';

type Ping = { t: string; lat: number; lon: number; course: number; speed_kn: number; mmsi: string };
type Track = { mmsi: string; name: string; type: string; flag: string; color: string; pings: Ping[] };
type Anomaly = { id: string; kind: string; mmsi: string; vessel: string; severity: string; lat: number; lon: number; partners?: string[] };
type Denied = { id: string; name: string; kind: string; polygon: [number, number][] };

interface Props {
  tracks: Track[];
  anomalies: Anomaly[];
  denied: Denied[];
  timeline: string[];
  step: number;
  showDenied: boolean;
  selectedMmsi: string | null;
  onSelect: (mmsi: string) => void;
}

export default function MarlinMap({
  tracks, anomalies, denied, timeline, step, showDenied, selectedMmsi, onSelect,
}: Props) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const leafletRef = useRef<L.Map | null>(null);
  const layersRef = useRef<{
    pings: L.LayerGroup;
    trails: L.LayerGroup;
    anomalies: L.LayerGroup;
    denied: L.LayerGroup;
  } | null>(null);

  // Init map
  useEffect(() => {
    if (!mapRef.current || leafletRef.current) return;
    const map = L.map(mapRef.current, {
      center: [21.0, 121.5],
      zoom: 7,
      zoomControl: true,
      attributionControl: true,
      preferCanvas: true,
    });
    // Primary: CartoDB Dark Matter (matches Kamiwaza dark theme)
    const darkLayer = L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      {
        attribution: '&copy; OpenStreetMap &copy; CARTO | MARLIN synthetic AIS',
        subdomains: 'abcd', maxZoom: 19,
        crossOrigin: true,
      },
    );
    let fallbackLayer: L.TileLayer | null = null;
    let dark404 = 0;
    darkLayer.on('tileerror', () => {
      dark404 += 1;
      // After several tile failures, fall back to OSM standard tiles
      if (dark404 >= 3 && !fallbackLayer) {
        fallbackLayer = L.tileLayer(
          'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
          {
            attribution: '&copy; OpenStreetMap contributors | MARLIN synthetic AIS',
            subdomains: 'abc', maxZoom: 19,
            crossOrigin: true,
          },
        );
        fallbackLayer.addTo(map);
        map.removeLayer(darkLayer);
      }
    });
    darkLayer.addTo(map);

    layersRef.current = {
      pings: L.layerGroup().addTo(map),
      trails: L.layerGroup().addTo(map),
      anomalies: L.layerGroup().addTo(map),
      denied: L.layerGroup().addTo(map),
    };
    leafletRef.current = map;
  }, []);

  // Render denied polygons
  useEffect(() => {
    if (!leafletRef.current || !layersRef.current) return;
    const lg = layersRef.current.denied;
    lg.clearLayers();
    if (!showDenied) return;
    denied.forEach((d) => {
      const fill = d.kind === 'denied' ? '#ff4d4d' : '#f5b942';
      const poly = L.polygon(d.polygon, {
        color: fill, weight: 2, fillColor: fill, fillOpacity: 0.18, dashArray: '6,4',
      }).bindTooltip(`<b>${d.name}</b><br/>${d.kind.toUpperCase()}`, { sticky: true, className: 'kw-tooltip' });
      poly.addTo(lg);
    });
  }, [denied, showDenied]);

  // Render pings + trails for the current step
  useEffect(() => {
    if (!leafletRef.current || !layersRef.current) return;
    const { pings, trails, anomalies: aLayer } = layersRef.current;
    pings.clearLayers();
    trails.clearLayers();
    aLayer.clearLayers();

    const tCutoff = timeline[step];
    const flaggedMmsis = new Set(anomalies.flatMap((a) => [a.mmsi, ...(a.partners || [])]));

    tracks.forEach((tr) => {
      // Pings up to current step
      const upto = tr.pings.filter((p) => p.t <= tCutoff);
      if (!upto.length) return;

      // Trail polyline (last 8 pings)
      const trailPts = upto.slice(-8).map((p) => [p.lat, p.lon] as [number, number]);
      if (trailPts.length > 1) {
        L.polyline(trailPts, {
          color: tr.color, weight: 1.4, opacity: 0.55,
        }).addTo(trails);
      }

      // Latest ping marker
      const last = upto[upto.length - 1];
      const flagged = flaggedMmsis.has(tr.mmsi);
      const isSel = selectedMmsi === tr.mmsi;
      const html = flagged
        ? `<div class="marker-flagged"></div>`
        : `<div class="marker-normal" style="background:${tr.color}"></div>`;
      const icon = L.divIcon({
        className: '',
        html: `<div style="transform:translate(-50%,-50%)${isSel ? ';outline:2px solid #00FFA7;outline-offset:3px;border-radius:50%;' : ''}">${html}</div>`,
        iconSize: [16, 16],
      });
      const marker = L.marker([last.lat, last.lon], { icon })
        .bindTooltip(
          `<b>${tr.name}</b><br/>${tr.type} • ${tr.flag} • MMSI ${tr.mmsi}<br/>` +
          `${last.lat.toFixed(3)}, ${last.lon.toFixed(3)} • ${last.speed_kn} kn`,
          { direction: 'top', offset: [0, -6] },
        )
        .on('click', () => onSelect(tr.mmsi));
      marker.addTo(pings);
    });

    // Render anomaly halos
    anomalies.forEach((a) => {
      L.circleMarker([a.lat, a.lon], {
        radius: 14, color: '#ff4d4d', weight: 1.5, opacity: 0.6,
        fillColor: '#ff4d4d', fillOpacity: 0.05,
      }).bindTooltip(`<b>${a.kind.toUpperCase()}</b> — ${a.vessel}`, { direction: 'top' })
        .addTo(aLayer);
    });
  }, [tracks, anomalies, timeline, step, selectedMmsi, onSelect]);

  return <div ref={mapRef} className="w-full h-full" />;
}
