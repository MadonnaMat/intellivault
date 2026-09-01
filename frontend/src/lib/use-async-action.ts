import { useState } from "react";
import type { ApiResult } from "./api";

/**
 * The loading/error bookkeeping shared by every "click -> call the backend ->
 * refresh or show the error" handler in the auth UI.
 */
export function useAsyncAction() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run<T>(
    action: () => Promise<ApiResult<T>>,
    opts: { onSuccess?: (data?: T) => void; fallback: string },
  ): Promise<void> {
    setLoading(true);
    setError(null);
    const result = await action();
    setLoading(false);
    if (result.ok) opts.onSuccess?.(result.data);
    else setError(result.error ?? opts.fallback);
  }

  return { loading, error, setError, run };
}
