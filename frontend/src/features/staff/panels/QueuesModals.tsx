import type React from "react";
import { useEffect, useState } from "react";

import { Modal } from "../../../components/ui/Modal";
import { EvidenceUpload } from "./EvidenceUpload";
import type { HardwareRequest } from "./Queues";

export type ReturnDueValues = {
  returnDueAt: string;
};

export type RejectRequestValues = {
  reason: string;
};

export type IssueReject = {
  item_id: number;
  broken: number;
  disposition: "needs_fix" | "remove";
};

export type AssignIssueValues = {
  boxCode: string;
  evidenceId: number;
  remark: string;
  rejects: IssueReject[];
};

export type ReturnRequestValues = {
  evidenceId: number;
  boxCode: string;
  remark: string;
  resolutions: Array<{ item_id: number; returned: number; damaged: number; missing: number }>;
};

type FormModalProps<T> = {
  row: HardwareRequest | null;
  open: boolean;
  pending: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (values: T) => void;
};

export function ReturnDueModal({
  row,
  open,
  pending,
  error,
  defaultValue,
  onClose,
  onSubmit,
}: FormModalProps<ReturnDueValues> & { defaultValue: string }) {
  const [returnDueAt, setReturnDueAt] = useState(defaultValue);

  useEffect(() => {
    if (open) setReturnDueAt(defaultValue);
  }, [defaultValue, open]);

  return (
    <Modal open={open} onClose={onClose} title={row ? `Set due for request #${row.id}` : "Set due"} footer={<FormFooter formId="return-due-form" pending={pending} submitLabel="Save due date" onCancel={onClose} />}>
      <form id="return-due-form" className="grid gap-3" onSubmit={(event) => submitForm(event, () => onSubmit({ returnDueAt }))}>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Return due date and time</span>
          <input className="desk-input" type="datetime-local" value={returnDueAt} disabled={pending} onChange={(event) => setReturnDueAt(event.target.value)} />
        </label>
        <ErrorText message={error} />
      </form>
    </Modal>
  );
}

export function RejectRequestModal({ row, open, pending, error, onClose, onSubmit }: FormModalProps<RejectRequestValues>) {
  const [reason, setReason] = useState("");
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    if (open) {
      setReason("");
      setValidationError("");
    }
  }, [open]);

  return (
    <Modal open={open} onClose={onClose} title={row ? `Reject request #${row.id}` : "Reject request"} footer={<FormFooter formId="reject-request-form" pending={pending} submitLabel="Reject request" onCancel={onClose} tone="danger" />}>
      <form
        id="reject-request-form"
        className="grid gap-3"
        onSubmit={(event) =>
          submitForm(event, () => {
            if (!reason.trim()) {
              setValidationError("Reason is required.");
              return;
            }
            onSubmit({ reason: reason.trim() });
          })
        }
      >
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Reason</span>
          <textarea className="desk-input min-h-24 w-full resize-y" value={reason} disabled={pending} onChange={(event) => setReason(event.target.value)} />
        </label>
        <ErrorText message={validationError || error} />
      </form>
    </Modal>
  );
}

export function AssignIssueModal({ row, open, pending, error, onClose, onSubmit, makerspaceId }: FormModalProps<AssignIssueValues> & { makerspaceId: number }) {
  const [boxCode, setBoxCode] = useState(row?.assigned_box?.code ?? "");
  const [evidenceId, setEvidenceId] = useState<number | null>(null);
  const [remark, setRemark] = useState("Issued from staff app.");
  const [rejects, setRejects] = useState<Record<number, { broken: number; disposition: "needs_fix" | "remove" }>>({});
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    if (open) {
      setBoxCode(row?.assigned_box?.code ?? "");
      setEvidenceId(null);
      setRemark("Issued from staff app.");
      setRejects({});
      setValidationError("");
    }
  }, [open, row]);

  const setBroken = (itemId: number, broken: number) =>
    setRejects((current) => ({
      ...current,
      [itemId]: { broken: Math.max(0, broken || 0), disposition: current[itemId]?.disposition ?? "needs_fix" },
    }));
  const setDisposition = (itemId: number, disposition: "needs_fix" | "remove") =>
    setRejects((current) => ({
      ...current,
      [itemId]: { broken: current[itemId]?.broken ?? 0, disposition },
    }));

  return (
    <Modal open={open} onClose={onClose} title={row ? `Assign and issue request #${row.id}` : "Assign and issue"} footer={<FormFooter formId="assign-issue-form" pending={pending} submitLabel="Assign + issue" onCancel={onClose} />}>
      <form
        id="assign-issue-form"
        className="grid gap-3"
        onSubmit={(event) =>
          submitForm(event, () => {
            if (!boxCode.trim()) {
              setValidationError("Box QR code is required.");
              return;
            }
            if (evidenceId === null) {
              setValidationError("Upload an issue photo before issuing.");
              return;
            }
            const overflow = (row?.items ?? []).find(
              (item) => (rejects[item.id]?.broken ?? 0) > item.accepted_quantity,
            );
            if (overflow) {
              setValidationError(`Can't reject more than ${overflow.accepted_quantity} of ${overflow.product_name}.`);
              return;
            }
            const rejectList = Object.entries(rejects)
              .filter(([, value]) => value.broken > 0)
              .map(([itemId, value]) => ({ item_id: Number(itemId), broken: value.broken, disposition: value.disposition }));
            onSubmit({ boxCode: boxCode.trim(), evidenceId, remark, rejects: rejectList });
          })
        }
      >
        {row?.assigned_box ? (
          <p className="text-xs text-muted">Box: <span className="font-medium text-ink">{row.assigned_box.label} ({row.assigned_box.code})</span></p>
        ) : null}
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Box QR code</span>
          <input className="desk-input" value={boxCode} disabled={pending} onChange={(event) => setBoxCode(event.target.value)} />
        </label>
        <div className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Issue photo</span>
          <EvidenceUpload makerspaceId={makerspaceId} evidenceType="issue" disabled={pending} onUploaded={setEvidenceId} />
        </div>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Remark</span>
          <textarea className="desk-input min-h-20 w-full resize-y" value={remark} disabled={pending} onChange={(event) => setRemark(event.target.value)} />
        </label>
        <div className="grid gap-2">
          <p className="text-sm font-medium text-ink">Items — reject any broken units</p>
          {row?.items.map((item) => {
            const reject = rejects[item.id];
            const broken = reject?.broken ?? 0;
            return (
              <div key={item.id} className="rounded-md border border-line p-2">
                <p className="text-sm font-medium text-ink">{item.product_name} <span className="text-muted">×{item.accepted_quantity}</span></p>
                <div className="mt-2 grid gap-2 sm:grid-cols-[auto_1fr] sm:items-end">
                  <label className="grid gap-1 text-xs text-muted">
                    <span>Reject as broken</span>
                    <input className="desk-input w-24" type="number" min="0" max={item.accepted_quantity} value={broken} disabled={pending} onChange={(event) => setBroken(item.id, Number(event.target.value))} />
                  </label>
                  {broken > 0 ? (
                    <label className="grid gap-1 text-xs text-muted">
                      <span>Send broken units to</span>
                      <select className="desk-input" value={reject?.disposition ?? "needs_fix"} disabled={pending} onChange={(event) => setDisposition(item.id, event.target.value as "needs_fix" | "remove")}>
                        <option value="needs_fix">To-be-fixed shelf</option>
                        <option value="remove">Remove from inventory</option>
                      </select>
                    </label>
                  ) : null}
                </div>
                {broken > 0 ? (
                  <p className="mt-1 text-xs text-muted">Issuing {Math.max(0, item.accepted_quantity - broken)}, {broken} not handed over.</p>
                ) : null}
              </div>
            );
          })}
        </div>
        <ErrorText message={validationError || error} />
      </form>
    </Modal>
  );
}

export function ReturnRequestModal({ row, open, pending, error, onClose, onSubmit, makerspaceId }: FormModalProps<ReturnRequestValues> & { makerspaceId: number }) {
  const [evidenceId, setEvidenceId] = useState<number | null>(null);
  const [boxCode, setBoxCode] = useState(row?.assigned_box?.code ?? "");
  const [remark, setRemark] = useState("");
  const [resolutions, setResolutions] = useState<ReturnRequestValues["resolutions"]>([]);
  const [validationError, setValidationError] = useState("");

  useEffect(() => {
    if (!open || !row) return;
    setEvidenceId(null);
    setBoxCode(row.assigned_box?.code ?? "");
    setRemark("");
    setValidationError("");
    setResolutions(row.items.map((item) => ({
      item_id: item.id,
      returned: item.issued_quantity - item.returned_quantity - item.damaged_quantity - item.missing_quantity,
      damaged: 0,
      missing: 0,
    })));
  }, [open, row]);

  const updateResolution = (itemId: number, key: "returned" | "damaged" | "missing", value: string) => {
    setResolutions((current) => current.map((resolution) => (resolution.item_id === itemId ? { ...resolution, [key]: Number(value) || 0 } : resolution)));
  };

  return (
    <Modal open={open} onClose={onClose} title={row ? `Return request #${row.id}` : "Return request"} footer={<FormFooter formId="return-request-form" pending={pending} submitLabel="Submit return" onCancel={onClose} />}>
      <form
        id="return-request-form"
        className="grid gap-3"
        onSubmit={(event) =>
          submitForm(event, () => {
            if (evidenceId === null) {
              setValidationError("Upload a return photo before submitting.");
              return;
            }
            if (!remark.trim()) {
              setValidationError("Return remark is required.");
              return;
            }
            if (resolutions.some((resolution) => !Number.isFinite(resolution.returned) || !Number.isFinite(resolution.damaged) || !Number.isFinite(resolution.missing))) {
              setValidationError("Resolution quantities must be numbers.");
              return;
            }
            if (resolutions.some((resolution) => resolution.returned < 0 || resolution.damaged < 0 || resolution.missing < 0)) {
              setValidationError("Resolution quantities cannot be negative.");
              return;
            }
            onSubmit({ evidenceId, boxCode: boxCode.trim(), remark: remark.trim(), resolutions });
          })
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1 text-sm">
            <span className="font-medium text-ink">Return photo</span>
            <EvidenceUpload makerspaceId={makerspaceId} evidenceType="return" disabled={pending} onUploaded={setEvidenceId} />
          </div>
          <label className="grid gap-1 text-sm">
            <span className="font-medium text-ink">Box QR code</span>
            <input className="desk-input" value={boxCode} disabled={pending} onChange={(event) => setBoxCode(event.target.value)} />
          </label>
        </div>
        <label className="grid gap-1 text-sm">
          <span className="font-medium text-ink">Remark</span>
          <textarea className="desk-input min-h-20 w-full resize-y" value={remark} disabled={pending} onChange={(event) => setRemark(event.target.value)} />
        </label>
        <div className="grid gap-2">
          <p className="text-sm font-medium text-ink">Resolution quantities</p>
          {row?.items.map((item) => {
            const resolution = resolutions.find((entry) => entry.item_id === item.id);
            return (
              <div key={item.id} className="rounded-md border border-line p-2">
                <p className="text-sm font-medium text-ink">{item.product_name}</p>
                <div className="mt-2 grid gap-2 sm:grid-cols-3">
                  {(["returned", "damaged", "missing"] as const).map((key) => (
                    <label key={key} className="grid gap-1 text-xs text-muted">
                      <span className="capitalize">{key}</span>
                      <input className="desk-input" type="number" min="0" value={resolution?.[key] ?? 0} disabled={pending} onChange={(event) => updateResolution(item.id, key, event.target.value)} />
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <ErrorText message={validationError || error} />
      </form>
    </Modal>
  );
}

function FormFooter({ formId, pending, submitLabel, tone = "default", onCancel }: { formId: string; pending: boolean; submitLabel: string; tone?: "danger" | "default"; onCancel: () => void }) {
  return (
    <div className="desk-actions flex flex-wrap justify-end gap-2">
      <button className="desk-button" type="button" disabled={pending} onClick={onCancel}>
        Cancel
      </button>
      <button className={tone === "danger" ? "desk-button bg-danger text-white" : "desk-button"} type="submit" form={formId} disabled={pending}>
        {pending ? "Working..." : submitLabel}
      </button>
    </div>
  );
}

function ErrorText({ message }: { message: string }) {
  return message ? <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{message}</p> : null;
}

function submitForm(event: React.FormEvent<HTMLFormElement>, submit: () => void) {
  event.preventDefault();
  submit();
}
