import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const mdClass = {
  p: "mb-soft leading-relaxed text-ink-primary",
  h1: "mb-wide text-2xl font-semibold text-ink-primary",
  h2: "mb-soft mt-broad text-lg font-semibold text-ink-primary",
  h3: "mb-base mt-wide text-base font-medium text-ink-primary",
  ul: "mb-soft list-disc space-y-tight pl-roomy text-ink-primary",
  ol: "mb-soft list-decimal space-y-tight pl-roomy text-ink-primary",
  li: "leading-relaxed",
  a: "text-accent underline hover:text-badge-accent",
  code: "rounded-tile bg-white/10 px-tight py-hair font-mono text-[0.9em] text-ink-primary",
  pre: "mb-soft overflow-x-auto rounded-card bg-black/40 p-soft text-sm text-ink-primary",
  blockquote: "mb-soft border-l-2 border-line-strong pl-soft text-ink-secondary",
  table: "my-soft w-full border-collapse text-sm",
  th: "border border-line bg-white/5 px-base py-tight text-left text-ink-primary",
  td: "border border-line px-base py-tight text-ink-primary",
};

export function LegalMarkdown(props: { markdown: string }) {
  return (
    <div className="prose-invert max-w-none text-sm">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className={mdClass.p}>{children}</p>,
          h1: ({ children }) => <h1 className={mdClass.h1}>{children}</h1>,
          h2: ({ children }) => <h2 className={mdClass.h2}>{children}</h2>,
          h3: ({ children }) => <h3 className={mdClass.h3}>{children}</h3>,
          ul: ({ children }) => <ul className={mdClass.ul}>{children}</ul>,
          ol: ({ children }) => <ol className={mdClass.ol}>{children}</ol>,
          li: ({ children }) => <li className={mdClass.li}>{children}</li>,
          a: ({ href, children }) => (
            <a href={href} className={mdClass.a} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          code: ({ className, children, ...rest }) => {
            const isBlock = String(className || "").includes("language-");
            if (isBlock) {
              return (
                <code className={`${mdClass.code} block whitespace-pre`} {...rest}>
                  {children}
                </code>
              );
            }
            return (
              <code className={mdClass.code} {...rest}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre className={mdClass.pre}>{children}</pre>,
          blockquote: ({ children }) => (
            <blockquote className={mdClass.blockquote}>{children}</blockquote>
          ),
          table: ({ children }) => <table className={mdClass.table}>{children}</table>,
          th: ({ children }) => <th className={mdClass.th}>{children}</th>,
          td: ({ children }) => <td className={mdClass.td}>{children}</td>,
        }}
      >
        {props.markdown}
      </ReactMarkdown>
    </div>
  );
}
