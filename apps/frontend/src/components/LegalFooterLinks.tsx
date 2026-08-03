import { NavLink } from "react-router-dom";
import { useLegalIndex } from "../features/legal/useLegalPages";

export function LegalFooterLinks() {
  const { index, loading } = useLegalIndex();
  if (loading || !index?.enabled || !index.pages.length) {
    return null;
  }

  return (
    <>
      {index.pages.map((page, i) => (
        <span key={page.slug} className="inline-flex items-center gap-x-4">
          {i > 0 ? (
            <span className="text-white/15" aria-hidden>
              ·
            </span>
          ) : null}
          <NavLink to={`/legal/${page.slug}`} className="hover:text-neutral-300">
            {page.title}
          </NavLink>
        </span>
      ))}
      <span className="text-white/15" aria-hidden>
        ·
      </span>
    </>
  );
}
