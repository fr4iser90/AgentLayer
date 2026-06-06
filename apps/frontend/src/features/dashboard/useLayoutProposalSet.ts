import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import {
  fetchLayoutProposalSet,
  type LayoutProposalSet,
} from "./layoutProposalShared";

export function useLayoutProposalSet(
  dashboardId: string,
  setId: string | null
): {
  loading: boolean;
  error: string | null;
  notFound: boolean;
  proposalSet: LayoutProposalSet | null;
} {
  const auth = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [proposalSet, setProposalSet] = useState<LayoutProposalSet | null>(null);

  useEffect(() => {
    if (!setId) {
      setProposalSet(null);
      setError(null);
      setNotFound(false);
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      setNotFound(false);
      try {
        const ps = await fetchLayoutProposalSet(auth, dashboardId, setId);
        if (cancelled) return;
        if (!ps) {
          setProposalSet(null);
          setNotFound(true);
          return;
        }
        setProposalSet(ps);
      } catch (e) {
        if (!cancelled) {
          setProposalSet(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, dashboardId, setId]);

  return { loading, error, notFound, proposalSet };
}
