import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const mdClass = {
  p: "mb-3 leading-relaxed text-neutral-200",
  h1: "mb-4 text-2xl font-semibold text-white",
  h2: "mb-3 mt-6 text-lg font-semibold text-white",
  h3: "mb-2 mt-4 text-base font-medium text-white",
  ul: "mb-3 list-disc space-y-1 pl-5 text-neutral-200",
  ol: "mb-3 list-decimal space-y-1 pl-5 text-neutral-200",
  li: "leading-relaxed",
  a: "text-sky-400 underline hover:text-sky-300",
  code: "rounded bg-white/10 px-1 py-0.5 font-mono text-[0.9em] text-neutral-100",
  pre: "mb-3 overflow-x-auto rounded-lg bg-black/40 p-3 text-sm text-neutral-100",
  blockquote: "mb-3 border-l-2 border-white/20 pl-3 text-neutral-300",
  table: "my-3 w-full border-collapse text-sm",
  th: "border border-white/10 bg-white/5 px-2 py-1 text-left text-white",
  td: "border border-white/10 px-2 py-1 text-neutral-200",
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
