import { Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export interface DeleteBlockedModalProps {
  vendorType: string;
  blockingIds: string[];
  onClose: () => void;
}

export function DeleteBlockedModal({
  vendorType,
  blockingIds,
  onClose,
}: DeleteBlockedModalProps) {
  const [copied, setCopied] = useState(false);
  const copyRef = useRef<HTMLButtonElement | null>(null);
  const n = blockingIds.length;

  useEffect(() => {
    // Initial focus: Copy IDs button (primary action per UI-SPEC)
    copyRef.current?.focus();
  }, []);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const handleCopyIds = async () => {
    try {
      await navigator.clipboard.writeText(blockingIds.join("\n"));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Silent fallback — admin dashboard runs on HTTPS/localhost, clipboard should work
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-blocked-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    >
      <div className="bg-surface-1 border border-border rounded-lg p-6 max-w-md w-full space-y-4">
        <h2
          id="delete-blocked-title"
          className="text-lg font-semibold text-gray-100"
        >
          Cannot delete template
        </h2>
        <p className="text-sm text-gray-300 leading-relaxed">
          The template{" "}
          <span className="font-mono text-gray-100">{vendorType}</span> has{" "}
          <span className="font-semibold text-gray-100">{n}</span>{" "}
          {n === 1 ? "profile" : "profiles"} still attached. Delete or reassign{" "}
          {n === 1 ? "it" : "them"} before removing the template.
        </p>
        <div className="bg-surface-2 border border-border rounded-md p-3 max-h-40 overflow-y-auto">
          <ul className="font-mono text-xs text-gray-400 space-y-1">
            {blockingIds.map((id) => (
              <li key={id}>{id}</li>
            ))}
          </ul>
        </div>
        <div className="flex items-center justify-between gap-2">
          <button
            ref={copyRef}
            onClick={handleCopyIds}
            className="btn-secondary flex items-center gap-1.5"
            type="button"
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{copied ? "Copied" : "Copy IDs"}</span>
          </button>
          <button
            onClick={onClose}
            className="btn-primary"
            type="button"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
