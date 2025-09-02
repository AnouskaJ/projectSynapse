import React from "react";

export default function StepEmbedMap({ url }) {
  if (!url) return null;
  return (
    <div className="h-72 w-full rounded-xl overflow-hidden border border-[var(--grab-edge)]">
      <iframe
        title="Google Directions"
        src={url}
        width="100%"
        height="100%"
        style={{ border: 0 }}
        loading="lazy"
        allowFullScreen
        referrerPolicy="no-referrer-when-downgrade"
      />
    </div>
  );
}
