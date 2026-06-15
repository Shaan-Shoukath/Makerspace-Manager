import type { Dispatch, FormEvent, SetStateAction } from "react";
import type { UseQueryResult } from "@tanstack/react-query";

import { Card } from "../../components/ui/Card";
import { FilePicker, TextArea, TextInput } from "./PublicPrintRequestParts";
import type { PrintBucket } from "./publicApi";

export type FormState = {
  bucketId: string;
  title: string;
  projectBrief: string;
  preferredSettings: string;
  material: string;
  color: string;
  quantity: number;
  sourceLink: string;
  contactEmail: string;
  contactPhone: string;
};

export const initialForm: FormState = {
  bucketId: "",
  title: "",
  projectBrief: "",
  preferredSettings: "",
  material: "",
  color: "",
  quantity: 1,
  sourceLink: "",
  contactEmail: "",
  contactPhone: "",
};

export function optional(value: string) {
  const trimmed = value.trim();
  return trimmed || undefined;
}

type PrintDetailsFormProps = {
  form: FormState;
  updateField: <K extends keyof FormState>(key: K, value: FormState[K]) => void;
  bucketsQuery: UseQueryResult<PrintBucket[], Error>;
  selectedBucket?: PrintBucket;
  modelFiles: File[];
  setModelFiles: Dispatch<SetStateAction<File[]>>;
  screenshotFiles: File[];
  setScreenshotFiles: Dispatch<SetStateAction<File[]>>;
  verified: boolean;
  submitPending: boolean;
  submitError?: Error | null;
  uploadProgress: string;
  website: string;
  onWebsiteChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export function PrintDetailsForm({
  form,
  updateField,
  bucketsQuery,
  selectedBucket,
  modelFiles,
  setModelFiles,
  screenshotFiles,
  setScreenshotFiles,
  verified,
  submitPending,
  submitError,
  uploadProgress,
  website,
  onWebsiteChange,
  onSubmit,
}: PrintDetailsFormProps) {
  return (
    <Card>
      <p className="text-xs font-semibold uppercase tracking-wide text-accent">
        Print Details
      </p>
      <form className="mt-4 space-y-4" onSubmit={onSubmit}>
        {/* Honeypot: hidden from humans; bots that autofill it trigger the server decoy. */}
        <input
          aria-hidden="true"
          autoComplete="off"
          className="hidden"
          name="website"
          tabIndex={-1}
          value={website}
          onChange={(event) => onWebsiteChange(event.target.value)}
        />
        <fieldset className="space-y-4" disabled={!verified || submitPending}>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                Bucket
              </span>
              <select
                className="desk-input w-full"
                required
                value={form.bucketId}
                onChange={(event) => updateField("bucketId", event.target.value)}
              >
                <option value="">Select a queue</option>
                {bucketsQuery.data?.map((bucket) => (
                  <option key={bucket.id} value={bucket.id}>
                    {bucket.name}
                  </option>
                ))}
              </select>
              {selectedBucket?.description ? (
                <p className="mt-1 text-xs text-muted">{selectedBucket.description}</p>
              ) : null}
              {bucketsQuery.isLoading ? (
                <p className="mt-1 text-xs text-muted">Loading queues...</p>
              ) : null}
              {bucketsQuery.isError ? (
                <p className="mt-1 text-xs text-danger">{bucketsQuery.error.message}</p>
              ) : null}
            </label>
            <TextInput
              label="Title"
              required
              value={form.title}
              onChange={(value) => updateField("title", value)}
            />
          </div>
          <TextArea
            label="Project brief"
            value={form.projectBrief}
            onChange={(value) => updateField("projectBrief", value)}
          />
          <TextArea
            label="Slicer settings / personal preferences"
            value={form.preferredSettings}
            onChange={(value) => updateField("preferredSettings", value)}
          />
          <div className="grid gap-4 md:grid-cols-2">
            <TextInput label="Material" value={form.material} onChange={(value) => updateField("material", value)} />
            <TextInput label="Color" value={form.color} onChange={(value) => updateField("color", value)} />
            <label className="block">
              <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted">
                Quantity
              </span>
              <input
                className="desk-input w-full"
                min={1}
                type="number"
                value={form.quantity}
                onChange={(event) =>
                  updateField("quantity", Math.max(1, Number(event.target.value) || 1))
                }
              />
            </label>
            <TextInput label="Source link" value={form.sourceLink} onChange={(value) => updateField("sourceLink", value)} />
            <TextInput label="Contact email" type="email" value={form.contactEmail} onChange={(value) => updateField("contactEmail", value)} />
            <TextInput label="Contact phone" value={form.contactPhone} onChange={(value) => updateField("contactPhone", value)} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <FilePicker
              accept=".stl,.3mf,.step,.stp,.obj"
              files={modelFiles}
              label="STL/model files"
              setFiles={setModelFiles}
            />
            <FilePicker
              accept="image/*,application/pdf"
              files={screenshotFiles}
              label="Estimated print-time screenshots (Bambu Lab)"
              setFiles={setScreenshotFiles}
            />
          </div>
        </fieldset>

        {!verified ? (
          <p className="rounded-md border border-line bg-surface px-3 py-2 text-sm text-muted">
            Verify your Check-In before submitting a print request.
          </p>
        ) : null}
        {uploadProgress ? <p className="text-sm text-muted">{uploadProgress}</p> : null}
        {submitError ? (
          <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
            {submitError.message}
          </p>
        ) : null}
        <button
          className="desk-button-primary w-full disabled:cursor-not-allowed disabled:opacity-50"
          disabled={!verified || !form.bucketId || !form.title.trim() || submitPending}
          type="submit"
        >
          {submitPending ? "Submitting..." : "Submit print request"}
        </button>
      </form>
    </Card>
  );
}
