"use client";

import { useState, type ReactNode } from "react";
import type { ResultPayload } from "@/lib/types";

function inline(s: string): ReactNode[] {
  return s
    .split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
    .map((p, i) =>
      p.startsWith("**") ? (
        <strong key={i}>{p.slice(2, -2)}</strong>
      ) : p.startsWith("`") ? (
        <code key={i} className="break-all rounded bg-sunk px-1">
          {p.slice(1, -1)}
        </code>
      ) : (
        p
      ),
    );
}



/** Small, safe markdown subset: headings, lists, fenced code, paragraphs. */
export function Markdown({ text }: { text: string }) {
  const out: ReactNode[] = [];
  const lines = text.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("```")) {
      const buf: string[] = [];
      i++;

      while (i < lines.length && !lines[i].startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }

      out.push(
        <pre
          key={`code-${i}`}
          className="box-border w-full min-w-0 max-w-full overflow-x-auto whitespace-pre-wrap break-words rounded-input border border-line bg-sunk p-3 text-sm"
        >
          <code className="break-words">{buf.join("\n")}</code>
        </pre>,
      );
    } else if (/^#{1,3} /.test(line)) {
      out.push(
        <h3
          key={i}
          className="mt-3 break-words text-lg font-bold"
        >
          {inline(line.replace(/^#+ /, ""))}
        </h3>,
      );
    } else if (/^\s*[-*] /.test(line)) {
      const items: string[] = [];

      while (i < lines.length && /^\s*[-*] /.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*] /, ""));
        i++;
      }

      i--;

      out.push(
        <ul
          key={`ul-${i}`}
          className="list-disc space-y-1 break-words pl-5"
        >
          {items.map((item, k) => (
            <li key={k}>{inline(item)}</li>
          ))}
        </ul>,
      );
    } else if (/^\d+\. /.test(line)) {
      const items: string[] = [];

      while (i < lines.length && /^\d+\. /.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\. /, ""));
        i++;
      }

      i--;

      out.push(
        <ol
          key={`ol-${i}`}
          className="list-decimal space-y-1 break-words pl-5"
        >
          {items.map((item, k) => (
            <li key={k}>{inline(item)}</li>
          ))}
        </ol>,
      );
    } else if (line.trim()) {
      out.push(
        <p key={i} className="break-words">
          {inline(line)}
        </p>,
      );
    }
  }

  return (
    <div className="min-w-0 max-w-full space-y-2 break-words">
      {out}
    </div>
  );
}

function Chart({
  c,
}: {
  c: NonNullable<ResultPayload["chart"]>;
}) {
  const max = Math.max(...c.values, 1);
  const bw = 360 / Math.max(c.labels.length, 1);

  return (
    <figure className="w-full min-w-0 max-w-full">
      <div className="w-full min-w-0 max-w-full overflow-hidden">
        <svg
          viewBox="0 0 400 200"
          role="img"
          aria-label={`${c.title}: ${c.labels
            .map((label, i) => `${label} ${c.values[i]}`)
            .join(", ")}`}
          className="block h-auto w-full max-w-full"
        >
          {c.values.map((value, i) => {
            const height = (value / max) * 140;

            return (
              <g key={i}>
                <rect
                  x={20 + i * bw + bw * 0.15}
                  y={160 - height}
                  width={bw * 0.7}
                  height={height}
                  rx="3"
                  fill="var(--acc)"
                  stroke="var(--ink)"
                />

                <text
                  x={20 + i * bw + bw / 2}
                  y={154 - height}
                  textAnchor="middle"
                  fontSize="11"
                  fill="var(--ink)"
                >
                  {value}
                </text>

                <text
                  x={20 + i * bw + bw / 2}
                  y={178}
                  textAnchor="middle"
                  fontSize="11"
                  fill="var(--mute)"
                >
                  {c.labels[i].slice(0, 12)}
                </text>
              </g>
            );
          })}

          <line
            x1="20"
            y1="160"
            x2="380"
            y2="160"
            stroke="var(--line)"
          />
        </svg>
      </div>

      <figcaption className="mt-1 break-words text-sm text-mute">
        {c.title}
      </figcaption>
    </figure>
  );
}

function Code({
  files,
}: {
  files: NonNullable<ResultPayload["files"]>;
}) {
  const [i, setI] = useState(0);
  const [copied, setCopied] = useState<string | null>(null);
  const file = files[Math.min(i, files.length - 1)];

  if (!file) {
    return (
      <p className="text-mute">
        The code step produced no files.
      </p>
    );
  }

  return (
    <div className="w-full min-w-0 max-w-full">
      <div
        role="tablist"
        aria-label="Files"
        className="mb-2 flex min-w-0 max-w-full flex-wrap gap-1.5"
      >
        {files.map((item, k) => (
          <button
            key={item.path}
            type="button"
            role="tab"
            aria-selected={k === i}
            onClick={() => setI(k)}
            className={`max-w-full break-all rounded-full border px-3 py-1 text-left text-sm ${
              k === i
                ? "border-ink bg-ink text-bg"
                : "border-line bg-sunk"
            }`}
          >
            {item.path}
          </button>
        ))}
      </div>

      <pre key={file.path} className="fx-rise box-border w-full min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words rounded-input border border-line bg-sunk p-3 text-sm">
        <code className="break-words">{file.content}</code>
      </pre>

      <button
        type="button"
        onClick={() => {
          navigator.clipboard?.writeText(file.content);
          setCopied(file.path);
          setTimeout(() => setCopied(null), 1600);
        }}
        className="mt-2 rounded-full border border-line bg-sunk px-3 py-1 text-sm"
      >
        {copied === file.path ? <span className="fx-ok inline-block">Copied ✓</span> : "Copy file"}
      </button>
    </div>
  );
}

function Gallery({
  images,
}: {
  images: NonNullable<ResultPayload["images"]>;
}) {
  if (!images.length) {
    return <p className="text-mute">No images were produced.</p>;
  }

  return (
    <div className="grid w-full min-w-0 max-w-full grid-cols-1 gap-3 sm:grid-cols-2">
      {images.map((image, i) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={i}
          alt={`Generated image ${i + 1}`}
          className="block h-auto w-full min-w-0 max-w-full rounded-input border border-line"
          src={
            image.b64
              ? `data:${image.mime ?? "image/png"};base64,${image.b64}`
              : image.url
          }
        />
      ))}
    </div>
  );
}

function download(name: string, text: string) {
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(
    new Blob([text], { type: "text/markdown" }),
  );
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}

export default function ResultView({
  r,
}: {
  r: ResultPayload;
}) {
  const bundle = () =>
    `# ${r.title}\n\n` +
    r.sections
      .map((section) => `## ${section.label}\n\n${section.text}`)
      .join("\n\n");

  return (
    <section
      aria-label="Result"
      className="fx-result box-border w-full min-w-0 max-w-full overflow-hidden rounded-panel border border-line bg-panel p-4 sm:p-5"
    >
      <h2 className="break-words text-2xl font-bold tracking-tight">
        Result
      </h2>

      {r.simulated && (
        <p
          role="note"
          className="mt-2 break-words rounded-input border border-acc bg-sunk p-2 text-sm"
        >
          Simulated output. Demo mode produced placeholders, not real work.
          Nothing here comes from a model or a search.
        </p>
      )}

      <p className="mt-2 break-words text-sm text-mute">
        {r.validation.passed === true
          ? "Checked against your requirements: passed."
          : r.validation.passed === false
            ? `Checked: issues remain after one revision. ${r.validation.issues.join("; ")}`
            : r.validation.note ?? "This result was not independently checked."}
      </p>

      <div className="fx-stagger mt-4 min-w-0 max-w-full space-y-5">
        {(r.kind === "research" || r.kind === "project") && (
          <>
            {r.findings && (
              <div className="min-w-0 max-w-full">
                <h3 className="mb-1 font-semibold">Findings</h3>
                <Markdown text={r.findings} />
              </div>
            )}

            <div className="min-w-0 max-w-full">
              <h3 className="mb-1 font-semibold">Sources</h3>

              {r.sources?.length ? (
                <ul className="min-w-0 max-w-full space-y-1.5">
                  {r.sources.map((source) => (
                    <li
                      key={source.url}
                      className="min-w-0 max-w-full rounded-input border border-line bg-sunk p-2"
                    >
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="break-all font-medium underline"
                      >
                        {source.title || source.url}
                      </a>

                      <span className="mt-1 block break-words text-sm text-mute">
                        {source.description}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-mute">
                  No sources were returned.
                </p>
              )}
            </div>
          </>
        )}

        {(r.kind === "code" || r.kind === "project") && r.files && (
          <div className="min-w-0 max-w-full">
            <h3 className="mb-1 font-semibold">Files</h3>
            <Code files={r.files} />
          </div>
        )}

        {(r.kind === "analysis" || r.kind === "project") && (
          <>
            {r.chart && <Chart c={r.chart} />}

            {r.insights && (
              <div className="min-w-0 max-w-full">
                <h3 className="mb-1 font-semibold">Insights</h3>
                <Markdown text={r.insights} />
              </div>
            )}
          </>
        )}

        {(r.kind === "image" || r.kind === "project") && r.images && (
          <div className="min-w-0 max-w-full">
            <h3 className="mb-1 font-semibold">Images</h3>
            <Gallery images={r.images} />
          </div>
        )}

        {(r.kind === "document" || r.kind === "strategy") && (
          <Markdown text={r.markdown} />
        )}

        {r.kind !== "image" && r.kind !== "project" && r.images && r.images.length > 0 && (
          <div className="min-w-0 max-w-full">
            <h3 className="mb-1 font-semibold">Images</h3>
            <Gallery images={r.images} />
          </div>
        )}

        {r.kind === "project" && (
          <div className="min-w-0 max-w-full">
            <h3 className="mb-1 font-semibold">Every step</h3>

            {r.sections.map((section) => (
              <details
                key={section.label}
                className="mb-1.5 min-w-0 max-w-full rounded-input border border-line bg-sunk p-2"
              >
                <summary className="cursor-pointer break-words font-medium">
                  {section.label}
                </summary>

                <div className="mt-2 min-w-0 max-w-full">
                  <Markdown text={section.text} />
                </div>
              </details>
            ))}
          </div>
        )}
      </div>

      <button
        type="button"
        onClick={() => download("flowio-result.md", bundle())}
        className="mt-5 max-w-full rounded-full border border-line bg-sunk px-4 py-1.5 text-sm"
      >
        Download as Markdown
      </button>
    </section>
  );
}
