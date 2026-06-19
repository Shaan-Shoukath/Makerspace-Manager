import { staffRequest } from "../../lib/api";
import { Panel } from "./StaffPanels";

export type DirectLoan = {
  id: number;
  public_token: string;
  status: string;
  target_label: string;
  container_label?: string | null;
  due_at: string | null;
  issued_by: { username: string; role: string } | null;
  return_evidence_id?: number | null;
  return_notes?: string;
  items: { product_name: string; quantity: number }[];
};

export function DirectLoanList({
  loans,
  onReturn,
}: {
  loans: DirectLoan[];
  onReturn: (loan: DirectLoan) => void;
}) {
  return (
    <Panel title="Direct handout loans">
      <div className="grid gap-2">
        {loans.map((loan) => (
          <article key={loan.id} className="rounded-md border border-line bg-surface p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="font-semibold text-ink">{loan.target_label}</h3>
                <p className="text-xs text-muted">
                  {loan.status}
                  {loan.container_label ? ` - given in: ${loan.container_label}` : ""}
                  {loan.due_at ? ` - due ${new Date(loan.due_at).toLocaleString()}` : ""}
                  {loan.issued_by ? ` - Issued by ${loan.issued_by.username}` : ""}
                </p>
              </div>
              {loan.status === "checked_out" ? (
                <button className="desk-button" onClick={() => onReturn(loan)}>
                  Return
                </button>
              ) : null}
            </div>
            <p className="mt-2 text-xs text-muted">
              {loan.items.map((item) => `${item.product_name} x${item.quantity}`).join(", ")}
            </p>
            {loan.status !== "checked_out" && loan.return_evidence_id ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <button className="desk-button text-xs" type="button" onClick={() => openEvidence(loan.return_evidence_id as number)}>
                  View return photo
                </button>
                {loan.return_notes ? <p className="text-xs text-muted">{loan.return_notes}</p> : null}
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </Panel>
  );
}

async function openEvidence(id: number) {
  try {
    const res = await staffRequest<{ url: string }>(`/admin/evidence/${id}`);
    window.open(res.url, "_blank", "noopener");
  } catch (error) {
    window.alert(error instanceof Error ? error.message : "Could not load evidence photo.");
  }
}
