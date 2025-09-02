import React, { useState } from "react";

export default function ImageAnswer({ onSubmit }) {
  const [files, setFiles] = useState(null);
  const [busy, setBusy] = useState(false);

  return (
    <div className="flex flex-col gap-2">
      <input type="file" accept="image/*" multiple onChange={(e) => setFiles(e.target.files)} className="input" />
      <button
        className="btn btn-primary"
        disabled={busy || !files?.length}
        onClick={async () => {
          setBusy(true);
          try {
            await onSubmit(files);
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Uploading…" : "Upload & Continue"}
      </button>
      <div className="text-xs text-gray-500">Tip: include the seal, any spillage, and the outer bag.</div>
    </div>
  );
}
