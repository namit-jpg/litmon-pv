import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

export type ToastKind = "success" | "error" | "info";

type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
  detail?: string;
};

type ToastCtx = {
  /** Show a transient confirmation. Returns nothing — toasts are fire-and-forget. */
  toast: (message: string, kind?: ToastKind, detail?: string) => void;
};

const Ctx = createContext<ToastCtx | null>(null);

// Long enough to read a sentence, short enough not to pile up during a demo.
const DISMISS_AFTER_MS = 5000;
// An error the user needs to act on should not vanish while they read it.
const ERROR_DISMISS_AFTER_MS = 9000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef<number[]>([]);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, kind: ToastKind = "success", detail?: string) => {
      const id = nextId.current++;
      setToasts((current) => {
        // Cap the stack so a loop of failures can't cover the whole screen.
        const next = [...current, { id, kind, message, detail }];
        return next.slice(-4);
      });
      const handle = window.setTimeout(
        () => dismiss(id),
        kind === "error" ? ERROR_DISMISS_AFTER_MS : DISMISS_AFTER_MS
      );
      timers.current.push(handle);
    },
    [dismiss]
  );

  // Clearing on unmount stops stray timers from firing into a dead tree.
  useEffect(
    () => () => {
      timers.current.forEach((handle) => window.clearTimeout(handle));
      timers.current = [];
    },
    []
  );

  const value = useMemo<ToastCtx>(() => ({ toast }), [toast]);

  return (
    <Ctx.Provider value={value}>
      {children}
      {/* aria-live so the confirmation is announced, not just shown. */}
      <div className="toast-stack" role="status" aria-live="polite">
        {toasts.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`toast toast-${t.kind}`}
            onClick={() => dismiss(t.id)}
            title="Dismiss"
          >
            <span className="toast-mark" aria-hidden="true">
              {t.kind === "success" ? "✓" : t.kind === "error" ? "!" : "i"}
            </span>
            <span className="toast-body">
              <strong>{t.message}</strong>
              {t.detail ? <span className="toast-detail">{t.detail}</span> : null}
            </span>
          </button>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(Ctx);
  // A missing provider should not crash a page mid-demo; degrade to a no-op.
  return ctx ?? { toast: () => {} };
}
