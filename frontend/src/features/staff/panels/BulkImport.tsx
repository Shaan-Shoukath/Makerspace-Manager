import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { Modal } from "../../../components/ui";
import { staffRequest } from "../../../lib/api";
import { Panel, type Makerspace } from "./shared";

type RawRow = Record<string, unknown>;
type Field = "name" | "total_quantity" | "available_quantity" | "description" | "storage_location" | "category";
type Mapping = Partial<Record<Field, string>>;
type ImportRow = { row: number; action?: string; data?: RawRow; errors?: Record<string, string> };
type ImportResult = {
  applied?: boolean;
  created?: number;
  updated?: number;
  valid?: boolean;
  summary?: { create?: number; update?: number; errors?: number; total?: number };
  rows?: ImportRow[];
  errors?: { row: number; errors: Record<string, string> }[];
};

const fields: Field[] = ["name", "total_quantity", "available_quantity", "description", "storage_location", "category"];
const aliases: Record<Field, string[]> = {
  name: ["name", "item", "product"],
  total_quantity: ["total", "total quantity", "quantity", "qty"],
  available_quantity: ["available", "available quantity", "in stock"],
  description: ["description", "details", "notes"],
  storage_location: ["location", "storage", "storage location", "shelf"],
  category: ["category", "category name", "type"],
};

export function BulkImport({ makerspace }: { makerspace: Makerspace }) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [rawJson, setRawJson] = useState('[{"name":"New Kit","total_quantity":"1","available_quantity":"1"}]');
  const [tableText, setTableText] = useState("");
  const [headers, setHeaders] = useState<string[]>([]);
  const [sourceRows, setSourceRows] = useState<RawRow[]>([]);
  const [mapping, setMapping] = useState<Mapping>({});
  const [mappingOpen, setMappingOpen] = useState(false);
  const [error, setError] = useState("");
  const mutation = useMutation({
    mutationFn: ({ apply, rows }: { apply: boolean; rows: RawRow[] }) =>
      staffRequest<ImportResult>(`/admin/makerspace/${makerspace.id}/inventory/import/${apply ? "apply" : "preview"}`, {
        method: "POST",
        body: JSON.stringify({ rows }),
      }),
  });
  const pending = mutation.isPending;
  const mappedRows = () => sourceRows.map((row) => mapRow(row, mapping));
  const submitRows = (apply: boolean, rows: RawRow[]) => {
    setError("");
    mutation.mutate({ apply, rows });
  };
  const submitJson = (apply: boolean) => {
    try {
      const parsed = JSON.parse(rawJson);
      if (!Array.isArray(parsed) || parsed.some((row) => !row || typeof row !== "object" || Array.isArray(row))) {
        setError("Advanced JSON must be an array of row objects.");
        return;
      }
      submitRows(apply, parsed as RawRow[]);
    } catch {
      setError("Advanced JSON could not be parsed. Check commas, quotes, and brackets.");
    }
  };
  const loadRows = (rows: RawRow[]) => {
    if (!rows.length) {
      setError("No rows were found.");
      return;
    }
    const nextHeaders = Object.keys(rows[0]);
    setSourceRows(rows);
    setHeaders(nextHeaders);
    setMapping(suggestMapping(nextHeaders));
    setMappingOpen(true);
    setError("");
  };
  return (
    <Panel title="Bulk import">
      <div className="grid gap-4">
        <div className="grid gap-2">
          <label className="text-xs font-semibold uppercase text-muted">Upload CSV or XLSX</label>
          <input
            className="desk-input"
            type="file"
            accept=".csv,.tsv,.xlsx"
            disabled={pending}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) parseFile(file).then(loadRows).catch((exc: Error) => setError(exc.message));
            }}
          />
        </div>
        <div className="grid gap-2">
          <label className="text-xs font-semibold uppercase text-muted">Paste table</label>
          <textarea className="desk-input h-28 w-full text-sm" value={tableText} onChange={(e) => setTableText(e.target.value)} />
          <div className="desk-actions flex flex-wrap gap-2">
            <button className="desk-button" type="button" disabled={pending || !tableText.trim()} onClick={() => loadRows(parseDelimited(tableText))}>
              Map pasted table
            </button>
            <button className="desk-button" type="button" disabled={pending || !sourceRows.length} onClick={() => setMappingOpen(true)}>
              Edit mapping
            </button>
            <button className="desk-button" type="button" disabled={pending || !sourceRows.length} onClick={() => submitRows(false, mappedRows())}>
              Preview
            </button>
            <button className="desk-button" type="button" disabled={pending || !sourceRows.length} onClick={() => submitRows(true, mappedRows())}>
              Apply
            </button>
          </div>
        </div>
        <details open={advancedOpen} onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}>
          <summary className="cursor-pointer text-sm font-semibold text-ink">Advanced JSON</summary>
          <textarea className="desk-input mt-2 h-32 w-full font-mono text-sm" value={rawJson} onChange={(e) => setRawJson(e.target.value)} />
          <div className="desk-actions mt-2 flex flex-wrap gap-2">
            <button className="desk-button" type="button" disabled={pending} onClick={() => submitJson(false)}>
              Preview JSON
            </button>
            <button className="desk-button" type="button" disabled={pending} onClick={() => submitJson(true)}>
              Apply JSON
            </button>
          </div>
        </details>
        {error ? <p className="text-sm text-danger">{error}</p> : null}
        {mutation.error ? <p className="text-sm text-danger">{mutation.error.message}</p> : null}
        {mutation.data ? <ImportSummary result={mutation.data} /> : null}
      </div>
      <Modal
        open={mappingOpen}
        onClose={() => setMappingOpen(false)}
        title="Map columns"
        footer={(
          <div className="desk-actions flex flex-wrap justify-end gap-2">
            <button className="desk-button" type="button" onClick={() => setMappingOpen(false)}>Cancel</button>
            <button className="desk-button" type="button" onClick={() => { setMappingOpen(false); submitRows(false, mappedRows()); }}>
              Preview
            </button>
          </div>
        )}
      >
        <div className="grid gap-3">
          {fields.map((field) => (
            <label key={field} className="grid gap-1 text-sm">
              <span className="font-medium text-ink">{labelFor(field)}</span>
              <select className="desk-input" value={mapping[field] ?? ""} onChange={(e) => setMapping((current) => ({ ...current, [field]: e.target.value || undefined }))}>
                <option value="">Do not import</option>
                {headers.map((header) => <option key={header} value={header}>{header}</option>)}
              </select>
            </label>
          ))}
        </div>
      </Modal>
    </Panel>
  );
}

function ImportSummary({ result }: { result: ImportResult }) {
  const errorRows = new Map((result.errors ?? []).map((item) => [item.row, item.errors]));
  return (
    <div className="grid gap-3 rounded-md border border-line bg-panel p-3">
      <div className="grid gap-2 text-sm sm:grid-cols-4">
        <Metric label="Create" value={result.created ?? result.summary?.create ?? 0} />
        <Metric label="Update" value={result.updated ?? result.summary?.update ?? 0} />
        <Metric label="Errors" value={result.summary?.errors ?? result.errors?.length ?? 0} />
        <Metric label="Rows" value={result.summary?.total ?? result.rows?.length ?? 0} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="text-xs uppercase text-muted"><tr><th className="px-2 py-1">Row</th><th className="px-2 py-1">Status</th><th className="px-2 py-1">Name</th><th className="px-2 py-1">Message</th></tr></thead>
          <tbody>
            {(result.rows ?? []).map((row) => {
              const errors = errorRows.get(row.row);
              return <tr key={row.row} className="border-t border-line"><td className="px-2 py-1">{row.row}</td><td className="px-2 py-1">{errors ? "error" : row.action ?? "ready"}</td><td className="px-2 py-1">{String(row.data?.name ?? "")}</td><td className="px-2 py-1 text-muted">{errors ? Object.entries(errors).map(([k, v]) => `${k}: ${v}`).join("; ") : ""}</td></tr>;
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div><p className="text-xs uppercase text-muted">{label}</p><p className="font-semibold text-ink">{value}</p></div>;
}

async function parseFile(file: File) {
  const data = await file.arrayBuffer();
  if (file.name.toLowerCase().endsWith(".xlsx")) {
    const XLSX = await import("xlsx");
    const workbook = XLSX.read(data, { type: "array" });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    return XLSX.utils.sheet_to_json<RawRow>(sheet, { defval: "" });
  }
  return parseDelimited(new TextDecoder().decode(data), file.name.toLowerCase().endsWith(".tsv") ? "\t" : undefined);
}

function parseDelimited(text: string, forcedDelimiter?: string) {
  const delimiter = forcedDelimiter ?? (text.includes("\t") ? "\t" : ",");
  const rows = csvRows(text, delimiter).filter((row) => row.some((cell) => cell.trim()));
  if (!rows.length) return [];
  const headers = rows[0].map((cell) => cell.trim());
  return rows.slice(1).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] ?? ""])));
}

function csvRows(text: string, delimiter: string) {
  const rows: string[][] = [[]];
  let value = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"' && text[i + 1] === '"') { value += '"'; i += 1; }
    else if (char === '"') quoted = !quoted;
    else if (char === delimiter && !quoted) { rows[rows.length - 1].push(value); value = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i += 1;
      rows[rows.length - 1].push(value); value = ""; rows.push([]);
    } else value += char;
  }
  rows[rows.length - 1].push(value);
  return rows;
}

// Normalize headers + aliases so "total_quantity", "Total Quantity", and
// "total quantity" all collapse to one form. This lets canonical snake_case
// headers (e.g. from an API export) auto-map instead of being dropped.
function normalizeHeader(value: string): string {
  return value.trim().toLowerCase().replace(/[_\s]+/g, " ");
}

function suggestMapping(headers: string[]): Mapping {
  return Object.fromEntries(
    fields
      .map((field) => {
        // The canonical field name itself is always an accepted header.
        const accepted = new Set([field, ...aliases[field]].map(normalizeHeader));
        return [field, headers.find((header) => accepted.has(normalizeHeader(header)))];
      })
      .filter(([, header]) => header),
  ) as Mapping;
}

function mapRow(row: RawRow, mapping: Mapping) {
  return Object.fromEntries(fields.map((field) => [field, mapping[field] ? row[mapping[field]] : undefined]).filter(([, value]) => value !== undefined && value !== "")) as RawRow;
}

function labelFor(field: Field) {
  return field.replace(/_/g, " ");
}
