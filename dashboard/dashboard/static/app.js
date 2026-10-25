"use strict";

// Playback console: shows and controls the server's shared replay clock (/api/playback).
// The clock lives on the server; this page only sends commands and renders the state it is told about.

const TZ = "Etc/GMT-1";           // the data's fixed UTC+1 time, no DST
const $ = (id) => document.getElementById(id);
const timeFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const dayFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });

let state = null;

function message(text, isError = false) {
  const el = $("message");
  el.textContent = text;
  el.classList.toggle("error", isError);
}

async function command(path, body) {
  try {
    const r = await fetch(`/api/playback/${path}`, {
      method: "POST", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined,
    });
    const b = await r.json();
    if (!r.ok) throw new Error(b.detail ?? r.status);
    message("");
    render(b);
  } catch (e) {
    message(`Command failed: ${e.message}`, true);
  }
}

function render(s) {
  state = s;
  const phase = !s.started ? "Not started" : s.phase === "warmup" ? "Warm-up (history)" : "Replay";
  $("clock-time").textContent = s.position ? timeFmt.format(new Date(s.position)) : "–";
  $("clock-phase").textContent = s.finished ? "End of the window" : phase;
  const pct = s.started ? Math.round(s.progress * 100) : null;
  $("clock-progress").textContent = pct === null ? "" : `${pct} % of the window`;
  $("bar-fill").style.width = `${s.started ? s.progress * 100 : 0}%`;
  $("bar").setAttribute("aria-valuenow", String(pct ?? 0));
  const w = s.window;
  $("window").textContent = `Window ${dayFmt.format(new Date(w.first))} to ${dayFmt.format(new Date(w.last))}; the replay proper starts ${dayFmt.format(new Date(w.replay_start))}, the days before are warm-up history.`;
  $("play").textContent = s.playing ? "Pause" : "Play";
  $("play").disabled = s.finished;
  if (document.activeElement !== $("speed")) $("speed").value = String(s.speed);
}

function listen() {
  const es = new EventSource("/api/playback/events");   // the browser reconnects by itself
  es.addEventListener("state", (ev) => { message(""); render(JSON.parse(ev.data)); });
  es.onerror = () => { if (es.readyState === EventSource.CLOSED) message("Lost the connection to the server.", true); else message("Reconnecting…"); };
}

async function services() {
  const check = async (id, url, ok) => {
    let up = false;
    try { const r = await fetch(url); up = r.ok && ok(await r.json()); } catch (_) { /* stays down */ }
    $(id).className = `dot ${up ? "up" : "down"}`;
    $(id).title = up ? "reachable" : "not reachable";
  };
  await Promise.all([
    check("svc-feed", "/api/playback", () => true),          // the clock needs the feed's window, so this answers only if the feed is up
    check("svc-twin", "/api/twin/status", (b) => b.available),
    check("svc-forecast", "/api/forecast/status", (b) => b.available),
  ]);
}

async function init() {
  $("play").addEventListener("click", () => command(state?.playing ? "pause" : "play"));
  $("reset").addEventListener("click", () => command("restart"));
  $("speed").addEventListener("change", (e) => command("speed", { speed: Number(e.target.value) }));
  try {
    const r = await fetch("/api/playback");
    if (!r.ok) throw new Error((await r.json()).detail ?? r.status);
    render(await r.json());
    listen();
  } catch (e) {
    message(`Cannot reach the replay feed. Is it running? (${e.message})`, true);
  }
  services();
  setInterval(services, 10000);
}

init();
