// MARLIN — AIS dark-vessel + anomaly intel layer
// Part of the MDM 2026 Hackathon Templates (https://github.com/12fn/MDMhackathon-repos)
// MIT licensed. Built on GAI (Government Acquisitions, Inc.) + Kamiwaza (https://www.kamiwaza.ai/).
'use client';

import dynamic from 'next/dynamic';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

const MarlinMap = dynamic(() => import('@/components/MarlinMap'), { ssr: false });

type Vessel = { mmsi: string; name: string; type: string; flag: string; color: string; ping_count: number };
type Track = { mmsi: string; name: string; type: string; flag: string; color: string; pings: any[] };
type Anomaly = { id: string; kind: string; mmsi: string; vessel: string; severity: string; lat: number; lon: number; partners?: string[]; summary: string };
type Denied = { id: string; name: string; kind: string; polygon: [number, number][] };
type Indicator = { id: string; type: string; confidence: number; timestamp: string; lat: number; lon: number; description: string; recommended_action: string };

export default function Page() {
  const [vessels, setVessels] = useState<Vessel[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [denied, setDenied] = useState<Denied[]>([]);
  const [timeline, setTimeline] = useState<string[]>([]);
  const [step, setStep] = useState(99);
  const [playing, setPlaying] = useState(false);
  const [showDenied, setShowDenied] = useState(true);
  const [selectedMmsi, setSelectedMmsi] = useState<string | null>(null);
  const [narrative, setNarrative] = useState<string>('');
  const [indicators, setIndicators] = useState<Indicator[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [showOnPrem, setShowOnPrem] = useState(false);
  const [health, setHealth] = useState<any>(null);
  const playRef = useRef<any>(null);

  // Initial load
  useEffect(() => {
    Promise.all([
      fetch('/api/vessels').then((r) => r.json()),
      fetch('/api/tracks').then((r) => r.json()),
      fetch('/api/anomalies').then((r) => r.json()),
      fetch('/api/denied').then((r) => r.json()),
      fetch('/api/timeline').then((r) => r.json()),
      fetch('/api/../health').then((r) => r.json()).catch(() => null),
    ]).then(([v, t, a, d, tl, h]) => {
      setVessels(v); setTracks(t); setAnomalies(a); setDenied(d); setTimeline(tl);
      if (h) setHealth(h);
    });
    fetch('http://127.0.0.1:8001/health').then((r) => r.json()).then(setHealth).catch(() => {});
  }, []);

  // Time slider play/pause
  useEffect(() => {
    if (!playing) { if (playRef.current) clearInterval(playRef.current); return; }
    playRef.current = setInterval(() => {
      setStep((s) => (s + 1 >= timeline.length ? 0 : s + 1));
    }, 120);
    return () => clearInterval(playRef.current);
  }, [playing, timeline.length]);

  const flaggedMmsis = useMemo(
    () => new Set(anomalies.flatMap((a) => [a.mmsi, ...(a.partners || [])])),
    [anomalies],
  );

  const selectedAnomaly = useMemo(
    () => anomalies.find((a) => a.mmsi === selectedMmsi || (a.partners || []).includes(selectedMmsi || '')),
    [anomalies, selectedMmsi],
  );

  const onSelect = useCallback((mmsi: string) => {
    setSelectedMmsi(mmsi);
    setNarrative('');
    setIndicators([]);
    if (!flaggedMmsis.has(mmsi)) return; // only run intel on flagged vessels for the demo
    runIntel(mmsi);
  }, [flaggedMmsis]);

  async function runIntel(mmsi: string) {
    setStreaming(true);
    setNarrative('');
    setIndicators([]);
    try {
      const res = await fetch(`http://127.0.0.1:8001/api/intel/${mmsi}/stream`, { method: 'POST' });
      if (!res.body) throw new Error('no stream body');
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        // Process SSE events line-by-line
        const events = buf.split('\n\n');
        buf = events.pop() || '';
        for (const evt of events) {
          const lines = evt.split('\n');
          let event = 'message';
          let data = '';
          for (const ln of lines) {
            if (ln.startsWith('event: ')) event = ln.slice(7).trim();
            else if (ln.startsWith('data: ')) data += ln.slice(6);
          }
          if (!data) continue;
          try {
            const obj = JSON.parse(data);
            if (event === 'token') setNarrative((n) => n + (obj.t || ''));
            else if (event === 'indicators') setIndicators(obj.indicators || []);
          } catch { /* ignore */ }
        }
      }
    } catch (e) {
      // Fall back to non-streaming
      try {
        const res = await fetch(`http://127.0.0.1:8001/api/intel/${mmsi}`, { method: 'POST' });
        const j = await res.json();
        setNarrative(j.narrative);
        setIndicators(j.indicators || []);
      } catch (e2) {
        setNarrative(`Error: ${(e2 as Error).message}`);
      }
    } finally {
      setStreaming(false);
    }
  }

  const sliderTime = timeline[step]?.replace('T', ' ').replace(/\..+/, '').replace(/\+.+/, '') || '';
  const stepPct = timeline.length ? `${(step / Math.max(1, timeline.length - 1)) * 100}%` : '0%';

  return (
    <div className="h-screen w-screen flex flex-col bg-kw-bg text-white overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-kw-border bg-kw-surface">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded bg-kw-primary flex items-center justify-center font-bold text-kw-bg">M</div>
          <div>
            <div className="font-semibold tracking-wide">MARLIN <span className="text-kw-muted text-xs ml-1">v1.0</span></div>
            <div className="text-xs text-kw-dim">Maritime Anomaly &amp; Risk Intelligence Layer — INDOPACOM Contested Logistics</div>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-kw-neon animate-pulse" />
            <span className="text-kw-dim">AIS feed</span>
            <span className="font-mono text-kw-primary">LIVE</span>
          </div>
          <div className="text-kw-dim">
            Provider: <span className="font-mono text-kw-primary">{health?.provider || '...'}</span>
          </div>
          <div className="text-kw-dim">
            Endpoint: <span className="font-mono text-kw-primary">{health?.endpoint || health?.kamiwaza_endpoint || '...'}</span>
          </div>
          <div className="text-kw-dim">
            Model: <span className="font-mono text-kw-primary">{health?.primary_model || '...'}</span>
          </div>
        </div>
      </header>

      {/* Body: map + side panel */}
      <main className="flex-1 flex min-h-0">
        {/* Map */}
        <div className="relative flex-1 min-w-0">
          <MarlinMap
            tracks={tracks}
            anomalies={anomalies}
            denied={denied}
            timeline={timeline}
            step={step}
            showDenied={showDenied}
            selectedMmsi={selectedMmsi}
            onSelect={onSelect}
          />

          {/* Top-left overlay: stats */}
          <div className="absolute z-[1000] top-3 left-3 bg-kw-surface/90 backdrop-blur border border-kw-border rounded px-3 py-2 text-xs space-y-1">
            <div className="flex gap-3"><span className="text-kw-dim">Vessels</span><span className="font-mono text-kw-primary">{vessels.length}</span></div>
            <div className="flex gap-3"><span className="text-kw-dim">Total pings</span><span className="font-mono text-kw-primary">{tracks.reduce((s, t) => s + t.pings.length, 0)}</span></div>
            <div className="flex gap-3"><span className="text-kw-dim">Anomalies</span><span className="font-mono text-red-400">{anomalies.length}</span></div>
            <div className="flex gap-3"><span className="text-kw-dim">Denied zones</span><span className="font-mono text-amber-400">{denied.length}</span></div>
          </div>

          {/* Top-right overlay: layer toggles */}
          <div className="absolute z-[1000] top-3 right-3 bg-kw-surface/90 backdrop-blur border border-kw-border rounded px-3 py-2 text-xs space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={showDenied} onChange={(e) => setShowDenied(e.target.checked)}
                     className="accent-kw-primary" />
              <span>Denied / restricted areas</span>
            </label>
            <button
              onClick={() => setShowOnPrem((v) => !v)}
              className="px-2 py-1 rounded bg-kw-primary text-kw-bg font-semibold text-xs hover:bg-kw-hover w-full"
            >
              {showOnPrem ? 'Hide' : 'Show'} on-prem swap
            </button>
          </div>

          {/* Bottom: time slider */}
          <div className="absolute z-[1000] bottom-3 left-3 right-[420px] bg-kw-surface/95 border border-kw-border rounded px-4 py-3">
            <div className="flex items-center gap-3 text-xs mb-2">
              <button
                onClick={() => setPlaying((p) => !p)}
                className="px-3 py-1 rounded bg-kw-primary text-kw-bg font-semibold hover:bg-kw-hover"
              >
                {playing ? 'Pause' : 'Play'}
              </button>
              <span className="text-kw-dim">Step</span>
              <span className="font-mono text-kw-primary">{step + 1}/{timeline.length}</span>
              <span className="text-kw-dim">UTC</span>
              <span className="font-mono text-white">{sliderTime}</span>
              <span className="ml-auto text-kw-dim">100-event playback @ 5-min cadence</span>
            </div>
            <input
              type="range" min={0} max={Math.max(0, timeline.length - 1)} value={step}
              onChange={(e) => setStep(parseInt(e.target.value))}
              className="kw-range w-full"
              style={{ ['--p' as any]: stepPct }}
            />
          </div>

          {/* On-prem terminal overlay */}
          {showOnPrem && (
            <div className="absolute z-[1000] bottom-24 right-[440px] w-[420px] bg-black/95 border border-kw-primary rounded p-3 font-mono text-xs">
              <div className="text-kw-dim mb-1">$ # swap to Kamiwaza on-prem — zero code change</div>
              <div className="terminal-line">$ export KAMIWAZA_BASE_URL=https://kamiwaza.local/api/v1</div>
              <div className="terminal-line">$ export KAMIWAZA_API_KEY=$( cat /etc/kamiwaza/key )</div>
              <div className="terminal-line">$ uvicorn backend.app:app --port 8001</div>
              <div className="text-kw-neon mt-1">[OK] MARLIN now serving from inside the SCIF.</div>
              <div className="text-kw-neon">[OK] 100% data containment. Nothing leaves the wire.</div>
              <div className="cursor-blink terminal-line"></div>
            </div>
          )}
        </div>

        {/* Side panel */}
        <aside className="w-[420px] border-l border-kw-border bg-kw-surface flex flex-col">
          <div className="p-4 border-b border-kw-border">
            <div className="text-xs text-kw-dim uppercase tracking-widest">Vessel Intel</div>
            {selectedMmsi ? (
              <div className="mt-1">
                <div className="text-lg font-semibold">
                  {tracks.find((t) => t.mmsi === selectedMmsi)?.name || selectedMmsi}
                </div>
                <div className="text-xs text-kw-dim">
                  MMSI {selectedMmsi} • {tracks.find((t) => t.mmsi === selectedMmsi)?.type} • {tracks.find((t) => t.mmsi === selectedMmsi)?.flag}
                </div>
                {selectedAnomaly && (
                  <div className="mt-2 inline-flex items-center gap-2 bg-red-500/10 border border-red-500/40 text-red-300 text-xs px-2 py-1 rounded">
                    <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
                    {selectedAnomaly.kind.replace('_', ' ').toUpperCase()} — {selectedAnomaly.severity.toUpperCase()}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-kw-dim mt-1">Click a red-pulsing vessel to generate intel.</div>
            )}
          </div>

          {/* Anomaly summary list — when nothing selected */}
          {!selectedMmsi && (
            <div className="p-4 space-y-3 overflow-auto scroll-hidden">
              <div className="text-xs uppercase tracking-widest text-kw-dim">Active Flags</div>
              {anomalies.map((a) => (
                <button
                  key={a.id}
                  onClick={() => onSelect(a.mmsi)}
                  className="w-full text-left bg-kw-surfaceHi border border-kw-border hover:border-kw-primary rounded p-3"
                >
                  <div className="flex items-center justify-between">
                    <div className="font-semibold text-sm">{a.vessel}</div>
                    <span className={`text-[10px] px-2 py-0.5 rounded uppercase ${
                      a.severity === 'critical' ? 'bg-red-500/20 text-red-300' :
                      a.severity === 'high' ? 'bg-amber-500/20 text-amber-300' :
                      'bg-kw-border text-kw-dim'
                    }`}>{a.severity}</span>
                  </div>
                  <div className="text-xs text-kw-primary mt-1">{a.kind.replace('_', ' ').toUpperCase()}</div>
                  <div className="text-xs text-kw-dim mt-1">{a.summary}</div>
                </button>
              ))}
            </div>
          )}

          {/* Narrative + indicators */}
          {selectedMmsi && (
            <div className="flex-1 overflow-auto scroll-hidden p-4 space-y-4">
              <div>
                <div className="text-xs uppercase tracking-widest text-kw-dim mb-2 flex items-center gap-2">
                  Intel Narrative
                  {streaming && <span className="text-kw-neon animate-pulse">streaming...</span>}
                </div>
                <div className="text-sm leading-relaxed whitespace-pre-wrap text-gray-200 bg-kw-surfaceHi border border-kw-border rounded p-3">
                  {narrative || (
                    flaggedMmsis.has(selectedMmsi)
                      ? 'Generating intel narrative via Kamiwaza Stack...'
                      : 'No anomalies on this vessel. Select a flagged (red) vessel for full intel.'
                  )}
                </div>
              </div>

              {indicators.length > 0 && (
                <div>
                  <div className="text-xs uppercase tracking-widest text-kw-dim mb-2">Structured Indicators (JSON-mode)</div>
                  <div className="space-y-2">
                    {indicators.map((ind) => (
                      <div key={ind.id} className="bg-kw-surfaceHi border border-kw-border rounded p-2 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-mono text-kw-primary">{ind.type}</span>
                          <span className="text-kw-dim">conf {(ind.confidence * 100).toFixed(0)}%</span>
                        </div>
                        <div className="mt-1 text-gray-300">{ind.description}</div>
                        <div className="mt-1 text-kw-neon">{ind.recommended_action}</div>
                        <div className="mt-1 text-kw-dim font-mono">
                          {ind.lat?.toFixed(3)}, {ind.lon?.toFixed(3)} @ {ind.timestamp?.replace('T', ' ').replace(/\..+/, '')}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="p-3 border-t border-kw-border text-xs text-kw-dim text-center">
            Powered by <span className="text-kw-primary font-semibold">Kamiwaza</span> — Orchestration without migration.
          </div>
        </aside>
      </main>
    </div>
  );
}
