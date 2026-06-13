import { useMemo } from "react";

import { useStaffGet } from "./shared";

type QrPrintPayload = {
  payload: string;
  svg: string;
};

export function QrImage({ qrId, label }: { qrId: number; label: string }) {
  const qr = useStaffGet<QrPrintPayload>(["qr-image", qrId], `/admin/qr/${qrId}/print`);
  const src = useMemo(() => {
    if (!qr.data?.svg) return "";
    return `data:image/svg+xml;utf8,${encodeURIComponent(qr.data.svg)}`;
  }, [qr.data?.svg]);

  if (qr.isLoading) {
    return <div className="grid aspect-square place-items-center rounded-md border border-line text-xs text-muted">Loading QR</div>;
  }

  if (qr.isError || !src) {
    return <div className="grid aspect-square place-items-center rounded-md border border-danger/40 text-xs text-danger">QR unavailable</div>;
  }

  return <img className="aspect-square w-full rounded-md border border-line bg-white p-2" src={src} alt={`${label} QR`} />;
}
