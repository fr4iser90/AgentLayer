import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { GalleryImage } from "./GalleryImage";
import { GalleryPublicSection } from "./gallery/GalleryPublicSection";
import { getPath } from "./dashboardDataPaths";
import type { UiBlock, UiLayout } from "./types";

function readHero(raw: unknown): { url: string; caption: string; headline: string } {
  if (raw && typeof raw === "object" && !Array.isArray(raw)) {
    const o = raw as Record<string, unknown>;
    return {
      url: String(o.url ?? "").trim(),
      caption: String(o.caption ?? ""),
      headline: String(o.headline ?? ""),
    };
  }
  return { url: "", caption: "", headline: "" };
}

function markdownText(block: UiBlock, data: Record<string, unknown>): string {
  const dp = block.props.dataPath || "";
  if (!dp) return "";
  const raw = getPath(data, dp);
  return typeof raw === "string" ? raw.trim() : "";
}

export function PublicGalleryShareView(props: {
  title: string;
  subtitle?: string;
  layout: UiLayout;
  data: Record<string, unknown>;
}) {
  const { t } = useTranslation(["dashboard"]);
  const { title, subtitle, layout, data } = props;

  const introTexts = useMemo(() => {
    const parts: string[] = [];
    for (const block of layout.blocks) {
      if (block.type === "markdown" || block.type === "rich_markdown") {
        const text = markdownText(block, data);
        if (text) parts.push(text);
      }
    }
    return parts;
  }, [layout.blocks, data]);

  const heroBlocks = layout.blocks.filter((b) => b.type === "hero");
  const galleryBlocks = layout.blocks.filter((b) => b.type === "gallery");

  return (
    <div className="min-h-dvh bg-neutral-950 text-ink-primary">
      <header className="sticky top-0 z-lift border-b border-line bg-neutral-950/85 px-wide py-wide backdrop-blur-md sm:px-deep sm:py-roomy">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {subtitle ? <p className="mt-tight text-sm text-ink-muted">{subtitle}</p> : null}
        {introTexts.length > 0 ? (
          <div className="mt-soft max-w-measure whitespace-pre-wrap text-sm leading-relaxed text-ink-secondary">
            {introTexts.join("\n\n")}
          </div>
        ) : null}
      </header>

      <main className="mx-auto w-full max-w-pageWide px-soft py-wide sm:px-broad sm:py-deep">
        {heroBlocks.map((block) => {
          const dp = block.props.dataPath || "hero";
          const hero = readHero(getPath(data, dp));
          if (!hero.url) return null;
          return (
            <section key={block.id} className="mb-broad sm:mb-page">
              <div className="relative aspect-[2.1/1] max-h-[min(520px,70vh)] w-full overflow-hidden rounded-sheet sm:rounded-sheet">
                <GalleryImage
                  url={hero.url}
                  alt={hero.headline || hero.caption || title}
                  className="h-full w-full object-cover"
                />
                {hero.headline || hero.caption ? (
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/35 to-transparent px-roomy pb-roomy pt-20">
                    {hero.headline ? (
                      <p className="text-lg font-medium sm:text-xl">{hero.headline}</p>
                    ) : null}
                    {hero.caption ? (
                      <p className="mt-tight text-sm text-ink-secondary">{hero.caption}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </section>
          );
        })}

        {galleryBlocks.map((block, sectionIndex) => {
          const sectionTitle =
            block.props.title?.trim() ||
            (galleryBlocks.length > 1
              ? t("dashboard:publicGallerySection", { n: sectionIndex + 1 })
              : "");
          return (
            <GalleryPublicSection
              key={block.id}
              block={block}
              sectionTitle={sectionTitle}
              data={data}
            />
          );
        })}
      </main>
    </div>
  );
}
