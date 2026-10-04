import { html, type TemplateResult } from "lit";

export type Tone = "positive" | "caution" | "negative" | "neutral";

export function status(label: string, tone: Tone): TemplateResult {
  return html`<span class="status" data-tone=${tone}><span class="status-dot" aria-hidden="true"></span>${label}</span>`;
}

export function panel(title: string, content: TemplateResult, action?: TemplateResult): TemplateResult {
  return html`<section class="panel" aria-label=${title}>
    <div class="panel-head"><h2>${title}</h2>${action ?? ""}</div>
    ${content}
  </section>`;
}

export function alert(title: string, detail: string, tone: Tone): TemplateResult {
  return html`<div class="alert" data-tone=${tone} role="status"><strong>${title}</strong><p>${detail}</p></div>`;
}

export function fact(label: string, value: string): TemplateResult {
  return html`<div class="fact"><dt>${label}</dt><dd>${value}</dd></div>`;
}

export function row(title: string, detail: string, state: TemplateResult): TemplateResult {
  return html`<div class="row"><div class="row-copy"><strong>${title}</strong><span>${detail}</span></div>${state}</div>`;
}

export function unavailableAction(label: string, reason: string): TemplateResult {
  return html`<div class="action-wrap"><button type="button" class="primary" disabled aria-describedby="action-reason">${label}</button><small id="action-reason">${reason}</small></div>`;
}
