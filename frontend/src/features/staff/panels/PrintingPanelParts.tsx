import type React from "react";
import { useEffect, useState } from "react";

import { Modal } from "../../../components/ui/Modal";
import { API_URL } from "../../../lib/api";

const API_V1_URL = API_URL.replace(/\/api$/, "/api/v1");
const ACCESS_TOKEN_KEY = "makerspace.access";

export type FilamentSpool = {
  id: number;
  makerspace: number;
  printer: number | null;
  printer_name?: string;
  material: string;
  color: string;
  brand: string;
  initial_weight_grams: string;
  remaining_weight_grams: string;
  is_active: boolean;
};

export type PrintPrinter = {
  id: number;
  makerspace: number;
  name: string;
  model: string;
  status: string;
  is_active: boolean;
  active_spool: FilamentSpool | null;
  current_request: { id: number; title: string; estimated_minutes: number } | null;
  is_free: boolean;
  pending_estimated_minutes: number;
  estimated_spool_remaining_after_queue_grams: string | null;
};

export type PrintRequest = {
  id: number;
  title: string;
  requester_username: string;
  status: string;
  material: string;
  color: string;
  estimated_minutes: number;
  estimated_filament_grams: string;
  printer: PrintPrinter | null;
  filament_spool: FilamentSpool | null;
};

export type PrinterPayload = {
  name: string;
  model: string;
  status: string;
  is_active: boolean;
};

export type SpoolPayload = {
  printer: number | null;
  material: string;
  color: string;
  brand: string;
  initial_weight_grams: string;
  remaining_weight_grams: string;
  is_active: boolean;
};

export async function printingRequest<T>(path: string, options: RequestInit = {}) {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  const response = await fetch(`${API_V1_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (response.ok) return (await response.json()) as T;
  const body = await response.json().catch(() => null);
  throw new Error(formatApiError(body, response.status));
}

export function formatApiError(body: unknown, status: number): string {
  const rendered = renderErrorValue(body);
  return rendered || `Request failed (${status})`;
}

function renderErrorValue(value: unknown, label?: string): string {
  if (!value) return "";
  if (typeof value === "string") return label ? `${humanize(label)}: ${value}` : value;
  if (Array.isArray(value)) {
    return value.map((item) => renderErrorValue(item, label)).filter(Boolean).join(" ");
  }
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => renderErrorValue(item, key))
      .filter(Boolean)
      .join(" ");
  }
  return label ? `${humanize(label)}: ${String(value)}` : String(value);
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/^\w/, (match) => match.toUpperCase());
}

export function ErrorText({ message }: { message?: string }) {
  return message ? <p className="mt-2 text-sm text-danger">{message}</p> : null;
}

export function PrinterCard({
  printer,
  onEdit,
  onDeactivate,
}: {
  printer: PrintPrinter;
  onEdit: () => void;
  onDeactivate: () => void;
}) {
  return (
    <div className="rounded-md border border-line bg-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold text-ink">{printer.name}</h3>
          <p className="text-xs text-muted">{printer.model || "No model"}</p>
        </div>
        <span className={`rounded-md px-2 py-1 text-xs font-semibold ${printer.is_free ? "bg-success/15 text-success" : "bg-warn/15 text-warn"}`}>
          {printer.is_free ? "Free" : "Busy"}
        </span>
      </div>
      <dl className="mt-3 grid gap-1 text-sm text-muted">
        <Row label="Status" value={`${printer.status}${printer.is_active ? "" : " (inactive)"}`} />
        <Row label="Pending" value={`${printer.pending_estimated_minutes} min`} />
        <Row label="Current" value={printer.current_request?.title ?? "None"} />
        <Row label="Spool" value={printer.active_spool ? `${printer.active_spool.material} ${printer.active_spool.color}` : "None"} />
        <Row label="Left after queue" value={`${printer.estimated_spool_remaining_after_queue_grams ?? "-"} g`} />
      </dl>
      <div className="desk-actions mt-3 flex flex-wrap gap-2">
        <button type="button" onClick={onEdit}>Edit</button>
        <button type="button" disabled={!printer.is_active} onClick={onDeactivate}>Deactivate</button>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-2"><dt>{label}</dt><dd className="text-right">{value}</dd></div>;
}

export function SpoolRow({
  spool,
  onEdit,
  onDeactivate,
}: {
  spool: FilamentSpool;
  onEdit: () => void;
  onDeactivate: () => void;
}) {
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="font-medium text-ink">{spool.material} {spool.color || ""}</span>
        <span className="text-muted">{spool.printer_name ?? "Unassigned"}</span>
        <span className="text-muted">{spool.remaining_weight_grams}g left of {spool.initial_weight_grams}g</span>
        <span className={spool.is_active ? "text-success" : "text-muted"}>{spool.is_active ? "Active" : "Inactive"}</span>
      </div>
      <div className="desk-actions mt-2 flex flex-wrap gap-2">
        <button type="button" onClick={onEdit}>Edit</button>
        <button type="button" disabled={!spool.is_active} onClick={onDeactivate}>Deactivate</button>
      </div>
    </div>
  );
}

export function PrintRows({
  title,
  rows,
  action,
}: {
  title: string;
  rows: PrintRequest[];
  action: (row: PrintRequest) => React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-line">
      <h3 className="border-b border-line bg-surface px-3 py-2 text-sm font-semibold text-muted">{title}</h3>
      <div className="grid gap-0">
        {rows.length ? rows.map((row) => (
          <article key={row.id} className="border-b border-line p-3 last:border-b-0">
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-ink">#{row.id} {row.title}</strong>
              <span className="rounded-md border border-line bg-bg px-2 py-0.5 text-xs text-muted">{row.status}</span>
              <div className="desk-actions ml-auto flex flex-wrap gap-2 text-sm">{action(row)}</div>
            </div>
            <p className="mt-2 text-xs text-muted">
              {row.requester_username} - {row.material || "material n/a"} {row.color || ""} - {row.estimated_minutes || 0} min - {row.estimated_filament_grams || "0.00"}g
            </p>
          </article>
        )) : <p className="p-3 text-sm text-muted">No print requests.</p>}
      </div>
    </div>
  );
}

export function PrinterEditDialog({
  printer,
  pending,
  error,
  onClose,
  onSubmit,
}: {
  printer: PrintPrinter | null;
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (payload: PrinterPayload) => void;
}) {
  const [form, setForm] = useState<PrinterPayload>({ name: "", model: "", status: "active", is_active: true });
  useEffect(() => {
    if (printer) setForm({ name: printer.name, model: printer.model, status: printer.status, is_active: printer.is_active });
  }, [printer]);
  return (
    <Modal open={Boolean(printer)} onClose={onClose} title="Edit printer" footer={<DialogActions pending={pending} disabled={!form.name.trim()} submitLabel="Save printer" onCancel={onClose} onSubmit={() => onSubmit(form)} />}>
      <PrinterFields form={form} onChange={setForm} />
      <ErrorText message={error} />
    </Modal>
  );
}

export function SpoolEditDialog({ spool, printers, pending, error, onClose, onSubmit }: {
  spool: FilamentSpool | null;
  printers: PrintPrinter[];
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (payload: SpoolPayload) => void;
}) {
  const [form, setForm] = useState<SpoolPayload>({ printer: null, material: "", color: "", brand: "", initial_weight_grams: "0", remaining_weight_grams: "0", is_active: true });
  useEffect(() => {
    if (spool) setForm({ printer: spool.printer, material: spool.material, color: spool.color, brand: spool.brand, initial_weight_grams: spool.initial_weight_grams, remaining_weight_grams: spool.remaining_weight_grams, is_active: spool.is_active });
  }, [spool]);
  return (
    <Modal open={Boolean(spool)} onClose={onClose} title="Edit spool" footer={<DialogActions pending={pending} disabled={!form.material.trim() || !form.initial_weight_grams || !form.remaining_weight_grams} submitLabel="Save spool" onCancel={onClose} onSubmit={() => onSubmit(form)} />}>
      <SpoolFields form={form} printers={printers} onChange={setForm} />
      <ErrorText message={error} />
    </Modal>
  );
}

export function FailPrintDialog({ open, pending, error, onClose, onSubmit }: {
  open: boolean;
  pending: boolean;
  error?: string;
  onClose: () => void;
  onSubmit: (reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  useEffect(() => { if (open) setReason(""); }, [open]);
  return (
    <Modal open={open} onClose={onClose} title="Fail print" footer={<DialogActions pending={pending} disabled={!reason.trim()} submitLabel="Submit failure" onCancel={onClose} onSubmit={() => onSubmit(reason.trim())} />}>
      <textarea className="desk-input min-h-28 w-full" placeholder="Failure reason" value={reason} onChange={(event) => setReason(event.target.value)} />
      <ErrorText message={error} />
    </Modal>
  );
}

function PrinterFields({ form, onChange }: { form: PrinterPayload; onChange: (form: PrinterPayload) => void }) {
  return (
    <div className="grid gap-3">
      <input className="desk-input" placeholder="Printer name" value={form.name} onChange={(event) => onChange({ ...form, name: event.target.value })} />
      <input className="desk-input" placeholder="Model" value={form.model} onChange={(event) => onChange({ ...form, model: event.target.value })} />
      <select className="desk-input" value={form.status} onChange={(event) => onChange({ ...form, status: event.target.value })}>
        <option value="active">Active</option>
        <option value="maintenance">Maintenance</option>
        <option value="offline">Offline</option>
      </select>
      <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={form.is_active} onChange={(event) => onChange({ ...form, is_active: event.target.checked })} /> Active</label>
    </div>
  );
}

function SpoolFields({ form, printers, onChange }: { form: SpoolPayload; printers: PrintPrinter[]; onChange: (form: SpoolPayload) => void }) {
  return (
    <div className="grid gap-3">
      <select className="desk-input" value={form.printer ?? ""} onChange={(event) => onChange({ ...form, printer: event.target.value ? Number(event.target.value) : null })}>
        <option value="">Unassigned printer</option>
        {printers.map((printer) => <option key={printer.id} value={printer.id}>{printer.name}</option>)}
      </select>
      <input className="desk-input" placeholder="Material" value={form.material} onChange={(event) => onChange({ ...form, material: event.target.value })} />
      <input className="desk-input" placeholder="Color" value={form.color} onChange={(event) => onChange({ ...form, color: event.target.value })} />
      <input className="desk-input" placeholder="Brand" value={form.brand} onChange={(event) => onChange({ ...form, brand: event.target.value })} />
      <input className="desk-input" type="number" min="0" placeholder="Initial weight g" value={form.initial_weight_grams} onChange={(event) => onChange({ ...form, initial_weight_grams: event.target.value })} />
      <input className="desk-input" type="number" min="0" placeholder="Remaining weight g" value={form.remaining_weight_grams} onChange={(event) => onChange({ ...form, remaining_weight_grams: event.target.value })} />
      <label className="flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={form.is_active} onChange={(event) => onChange({ ...form, is_active: event.target.checked })} /> Active</label>
    </div>
  );
}

function DialogActions({ pending, disabled, submitLabel, onCancel, onSubmit }: {
  pending: boolean;
  disabled: boolean;
  submitLabel: string;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <div className="desk-actions flex flex-wrap justify-end gap-2">
      <button type="button" disabled={pending} onClick={onCancel}>Cancel</button>
      <button type="button" disabled={pending || disabled} onClick={onSubmit}>{pending ? "Saving..." : submitLabel}</button>
    </div>
  );
}
