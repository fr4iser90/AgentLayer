import { useEffect, useState } from "react";

export type LegalPageLink = {
  slug: string;
  title: string;
  href: string;
};

export type LegalIndex = {
  enabled: boolean;
  jurisdiction: string;
  terms_enabled: boolean;
  pages: LegalPageLink[];
};

export type LegalPageContent = {
  slug: string;
  title: string;
  body_md: string;
};

let cachedIndex: LegalIndex | null = null;
let indexPromise: Promise<LegalIndex> | null = null;

async function fetchLegalIndex(): Promise<LegalIndex> {
  const res = await fetch("/v1/public/legal", { credentials: "include" });
  if (!res.ok) {
    return { enabled: false, jurisdiction: "none", terms_enabled: false, pages: [] };
  }
  return (await res.json()) as LegalIndex;
}

export function useLegalIndex(): { index: LegalIndex | null; loading: boolean } {
  const [index, setIndex] = useState<LegalIndex | null>(cachedIndex);
  const [loading, setLoading] = useState(!cachedIndex);

  useEffect(() => {
    if (cachedIndex) {
      setIndex(cachedIndex);
      setLoading(false);
      return;
    }
    if (!indexPromise) {
      indexPromise = fetchLegalIndex().then((data) => {
        cachedIndex = data;
        return data;
      });
    }
    let active = true;
    indexPromise
      .then((data) => {
        if (active) {
          setIndex(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setIndex({ enabled: false, jurisdiction: "none", terms_enabled: false, pages: [] });
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return { index, loading };
}

export async function fetchLegalPage(slug: string): Promise<LegalPageContent | null> {
  const res = await fetch(`/v1/public/legal/${encodeURIComponent(slug)}`, {
    credentials: "include",
  });
  if (!res.ok) return null;
  return (await res.json()) as LegalPageContent;
}

export function invalidateLegalIndexCache(): void {
  cachedIndex = null;
  indexPromise = null;
}
