import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { GalleryImage } from "./GalleryImage";
import { getPath } from "./dashboardDataPaths";
import type { UiBlock, UiLayout } from "./types";

type PhotoRow = { id?: unknown; url?: unknown; caption?: unknown };

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

function galleryPhotos(block: UiBlock, data: Record<string, unknown>): PhotoRow[] {
  const dp = block.props.dataPath || "";
  if (!dp) return [];
  const raw = getPath(data, dp);
  if (!Array.isArray(raw)) return [];
  return raw as PhotoRow[];
}

function PublicPhotoTile(props: { url: string; caption: string }) {
  const { url, caption } = props;
  if (!url) return null;
  return (
    <figure className="group overflow-hidden rounded-lg bg-black/40 sm:rounded-xl">
      <div className="aspect-square w-full overflow-hidden bg-neutral-900">
        <GalleryImage
          url={url}
          alt={caption || "Photo"}
          className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
        />
      </div>
      {caption ? (
        <figcaption className="border-t border-white/5 px-3 py-2 text-xs leading-relaxed text-neutral-300">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
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
    <div className="min-h-dvh bg-neutral-950 text-white">
      <header className="sticky top-0 z-20 border-b border-white/10 bg-neutral-950/85 px-4 py-4 backdrop-blur-md sm:px-8 sm:py-5">
        <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-neutral-400">{subtitle}</p> : null}
        {introTexts.length > 0 ? (
          <div className="mt-3 max-w-2xl whitespace-pre-wrap text-sm leading-relaxed text-neutral-300">
            {introTexts.join("\n\n")}
          </div>
        ) : null}
      </header>

      <main className="mx-auto w-full max-w-[1600px] px-3 py-4 sm:px-6 sm:py-8">
        {heroBlocks.map((block) => {
          const dp = block.props.dataPath || "hero";
          const hero = readHero(getPath(data, dp));
          if (!hero.url) return null;
          return (
            <section key={block.id} className="mb-6 sm:mb-10">
              <div className="relative aspect-[2.1/1] max-h-[min(520px,70vh)] w-full overflow-hidden rounded-xl sm:rounded-2xl">
                <GalleryImage
                  url={hero.url}
                  alt={hero.headline || hero.caption || title}
                  className="h-full w-full object-cover"
                />
                {hero.headline || hero.caption ? (
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/35 to-transparent px-5 pb-5 pt-20">
                    {hero.headline ? (
                      <p className="text-lg font-medium sm:text-xl">{hero.headline}</p>
                    ) : null}
                    {hero.caption ? (
                      <p className="mt-1 text-sm text-neutral-300">{hero.caption}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </section>
          );
        })}

        {galleryBlocks.map((block, sectionIndex) => {
          const photos = galleryPhotos(block, data).filter((p) =>
            String(p.url ?? "").trim()
          );
          const sectionTitle =
            block.props.title?.trim() ||
            (galleryBlocks.length > 1
              ? t("dashboard:publicGallerySection", { n: sectionIndex + 1 })
              : "");
          return (
            <section key={block.id} className="mb-8 last:mb-4 sm:mb-12">
              {sectionTitle ? (
                <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-neutral-400 sm:mb-4">
                  {sectionTitle}
                </h2>
              ) : null}
              {photos.length === 0 ? (
                <p className="py-16 text-center text-sm text-neutral-500">
                  {t("dashboard:photosEmptyReadOnly")}
                </p>
              ) : (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-3 lg:grid-cols-4 lg:gap-4 xl:grid-cols-5">
                  {photos.map((row, ri) => (
                    <PublicPhotoTile
                      key={String(row.id ?? ri)}
                      url={String(row.url ?? "").trim()}
                      caption={String(row.caption ?? "")}
                    />
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </main>
    </div>
  );
}
