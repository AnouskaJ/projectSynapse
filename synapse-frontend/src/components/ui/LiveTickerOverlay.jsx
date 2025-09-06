import { useEffect, useState } from "react";

export default function LiveTickerOverlay({
  onClose,
  line1 = "Real-time feed connected",
  line2 = "Driver locations updating every 10s",
}) {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    if (!visible) onClose?.();
  }, [visible, onClose]);

  if (!visible) return null;

  return (
    <div className="gt-ticker" role="status" aria-live="polite">
      <span className="live">Live</span>
      <span className="gt-dim">{line1}</span>
      <span className="gt-dim">{line2}</span>

      <button
        className="gt-ticker-close"
        aria-label="Hide live feed"
        title="Hide"
        onClick={() => setVisible(false)}
      >
        ×
      </button>
    </div>
  );
}
