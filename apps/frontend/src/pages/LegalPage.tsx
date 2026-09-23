import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { LegalMarkdown } from "../features/legal/LegalMarkdown";
import { fetchLegalPage, type LegalPageContent } from "../features/legal/useLegalPages";

export function LegalPage() {
  const { slug = "" } = useParams<{ slug: string }>();
  const { t } = useTranslation(["common"]);
  const [page, setPage] = useState<LegalPageContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setMissing(false);
    fetchLegalPage(slug)
      .then((data) => {
        if (!active) return;
        if (!data) {
          setMissing(true);
          setPage(null);
        } else {
          setPage(data);
        }
        setLoading(false);
      })
      .catch(() => {
        if (!active) return;
        setMissing(true);
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [slug]);

  return (
    <div className="h-full min-h-0 overflow-y-auto">
      <div className="mx-auto max-w-3xl px-broad py-page">
        <p className="mb-broad">
          <Link to="/login" className="text-sm text-sky-400 hover:underline">
            {t("legal.back")}
          </Link>
        </p>
        {loading ? (
          <p className="text-sm text-ink-muted">{t("nav.loading")}</p>
        ) : missing || !page ? (
          <p className="text-sm text-ink-muted">{t("legal.notFound")}</p>
        ) : (
          <>
            <h1 className="mb-broad text-2xl font-semibold text-ink-primary">{page.title}</h1>
            <LegalMarkdown markdown={page.body_md} />
          </>
        )}
      </div>
    </div>
  );
}
