import { css } from "lit";

export const styles = css`
  :host { display: block; font: 14px/1.5 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  *, *::before, *::after { box-sizing: border-box; }
  .light { --canvas: #f5f7f9; --surface: #fff; --border: #dce2e8; --text: #202b35; --muted: #586875; --accent: #037da7; --accent-soft: #e9f5f9; --positive: #24734a; --positive-bg: #eaf5ef; --caution: #936019; --caution-bg: #fff5e5; --negative: #a43a39; --negative-bg: #fcf0ef; --neutral-bg: #eef1f3; }
  .dark { --canvas: #111a22; --surface: #1c2933; --border: #3d4e5b; --text: #edf2f4; --muted: #b5c3cc; --accent: #62c8eb; --accent-soft: #153847; --positive: #88d6a7; --positive-bg: #183a2b; --caution: #f6c977; --caution-bg: #47351d; --negative: #f5a09c; --negative-bg: #492c2c; --neutral-bg: #30404b; }
  .light, .dark { min-height: 100vh; color: var(--text); background: var(--canvas); }
  button, select { font: inherit; }
  :is(button, select, a):focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
  .skip-link { position: absolute; top: -100px; left: 16px; z-index: 3; padding: 9px 14px; border: 1px solid var(--border); background: var(--surface); color: var(--text); }
  .skip-link:focus { top: 10px; }
  .topbar, .tabs { background: var(--surface); border-bottom: 1px solid var(--border); }
  .topbar-inner, .tabs-inner { max-width: 1120px; margin: auto; display: flex; align-items: center; }
  .topbar-inner { min-height: 60px; padding: 0 20px; justify-content: space-between; }
  .brand { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .brand strong { font-size: 18px; letter-spacing: -.02em; }
  .brand-mark { display: inline-grid; place-items: center; width: 30px; height: 30px; border-radius: 9px; background: var(--accent); color: var(--surface); font-size: 21px; }
  .fixture-label { margin-left: 10px; padding-left: 18px; border-left: 1px solid var(--border); color: var(--muted); font-size: 12px; }
  .theme-button { width: 40px; height: 40px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--text); cursor: pointer; font-size: 20px; }
  .tabs { overflow-x: auto; }
  .tabs-inner { padding: 0 12px; white-space: nowrap; }
  .tabs a { display: inline-flex; align-items: center; min-height: 48px; padding: 0 14px; border-bottom: 2px solid transparent; color: var(--muted); text-decoration: none; }
  .tabs a:hover { color: var(--text); background: var(--canvas); }
  .tabs a[aria-current="page"] { color: var(--text); border-bottom-color: var(--accent); font-weight: 650; }
  main { max-width: 1120px; margin: 0 auto; padding: 24px 20px 64px; }
  main:focus { outline: none; }
  .review-banner { display: flex; gap: 16px; align-items: center; justify-content: space-between; padding: 12px 16px; border: 1px solid var(--border); border-radius: 9px; background: var(--accent-soft); }
  .review-banner label { display: flex; align-items: center; gap: 10px; white-space: nowrap; font-weight: 600; }
  select { min-height: 40px; padding: 0 32px 0 10px; border: 1px solid var(--border); border-radius: 7px; color: var(--text); background: var(--surface); }
  .page-heading { margin: 30px 0 22px; }
  .eyebrow { margin: 0 0 2px; color: var(--accent); text-transform: uppercase; letter-spacing: .08em; font-size: 11px; font-weight: 700; }
  h1 { margin: 0; font-size: clamp(25px, 3vw, 32px); line-height: 1.2; letter-spacing: -.025em; }
  h1:focus { outline: none; }
  .page-heading p:last-child { margin: 8px 0 0; color: var(--muted); }
  .alert { margin: 0 0 18px; padding: 13px 16px; border: 1px solid var(--border); border-left: 4px solid var(--accent); border-radius: 8px; background: var(--surface); }
  .alert[data-tone="positive"] { border-left-color: var(--positive); }
  .alert[data-tone="caution"] { border-left-color: var(--caution); }
  .alert[data-tone="negative"] { border-left-color: var(--negative); }
  .alert p { margin: 3px 0 0; color: var(--muted); }
  .metric-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
  .metric-grid .panel { margin: 0; }
  .metric { margin: 4px 0; font-size: 26px; font-weight: 650; letter-spacing: -.03em; }
  .panel { min-width: 0; margin: 0 0 18px; padding: 18px 20px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); }
  .panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 12px; }
  h2 { margin: 0; font-size: 17px; font-weight: 650; }
  .muted { color: var(--muted); }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 13px 0; border-top: 1px solid var(--border); }
  .row-copy { display: grid; gap: 3px; min-width: 0; }
  .row-copy span { color: var(--muted); overflow-wrap: anywhere; }
  .status { display: inline-flex; align-items: center; gap: 7px; flex-shrink: 0; padding: 4px 9px; border-radius: 20px; background: var(--neutral-bg); color: var(--text); font-size: 12px; font-weight: 650; white-space: nowrap; }
  .status[data-tone="positive"] { background: var(--positive-bg); color: var(--positive); }
  .status[data-tone="caution"] { background: var(--caution-bg); color: var(--caution); }
  .status[data-tone="negative"] { background: var(--negative-bg); color: var(--negative); }
  .status-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .facts { margin: 0 0 12px; }
  .fact { display: grid; grid-template-columns: minmax(110px, 28%) 1fr; gap: 12px; padding: 10px 0; border-top: 1px solid var(--border); }
  .fact dt { color: var(--muted); }
  .fact dd { margin: 0; font-weight: 550; overflow-wrap: anywhere; }
  .two-column { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
  .action-wrap { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
  .action-wrap small { color: var(--muted); }
  .primary { min-height: 40px; padding: 0 15px; border: 1px solid var(--border); border-radius: 8px; background: var(--accent); color: var(--surface); font-weight: 650; }
  .primary:disabled { background: var(--neutral-bg); color: var(--muted); cursor: not-allowed; }
  footer { padding: 22px 20px; border-top: 1px solid var(--border); color: var(--muted); text-align: center; font-size: 12px; }
  @media (max-width: 700px) { .metric-grid, .two-column { grid-template-columns: 1fr; } .review-banner { align-items: stretch; flex-direction: column; } .review-banner label { justify-content: space-between; } .row { align-items: flex-start; flex-direction: column; gap: 8px; } }
  @media (max-width: 480px) { .fixture-label { display: none; } main { padding: 16px 14px 48px; } .panel { padding: 14px 15px; } .topbar-inner { padding: 0 14px; } .fact { grid-template-columns: 1fr; gap: 2px; } }
  @media (forced-colors: active) { .status, .alert, .panel, .primary { border: 1px solid CanvasText; } .tabs a[aria-current="page"] { border-bottom-color: Highlight; } }
  @media (prefers-reduced-motion: no-preference) { .tabs a, .theme-button { transition: background-color .15s ease, color .15s ease; } }
`;
