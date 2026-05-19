/**
 * MarkdownView — react-markdown wrapper styled with Village tokens.
 * Fraunces headings, Manrope body, Geist Mono code blocks, amber links.
 * Used for rendering task documents, agent reports, and analyses.
 */
"use client";

import * as React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CitedContextItem } from "@/lib/types";

export interface MarkdownViewProps {
  body: string;
  className?: string;
  /** "compact" tightens spacing for inline use (task detail). "article" is reading mode. */
  variant?: "compact" | "article";
  /**
   * Source citations from the agent that wrote this document. When provided
   * and non-empty, renders a "Sources" rail alongside the body so the operator
   * can audit what context the agent drew from. Drawn from task_documents.cited_context.
   */
  citedContext?: CitedContextItem[] | null;
}

export function MarkdownView({ body, className, variant = "compact", citedContext }: MarkdownViewProps) {
  const proseClass = variant === "article" ? "prose-article" : "prose-compact";
  const sources = (citedContext ?? []).filter((c) => c.path);
  const hasSources = sources.length > 0;
  return (
    <div className={cn("markdown-view-wrapper", hasSources && "grid grid-cols-[1fr_auto] gap-6 items-start", className)}>
      <div className={cn("markdown-view", proseClass, "min-w-0")}>
        <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="font-heading text-4xl mt-6 mb-4 first:mt-0">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="font-heading text-3xl mt-6 mb-3 first:mt-0">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="font-heading text-2xl mt-5 mb-2 first:mt-0">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="font-heading text-xl mt-4 mb-2 first:mt-0">{children}</h4>
          ),
          p: ({ children }) => (
            <p className="mb-3 leading-relaxed text-foreground/90">{children}</p>
          ),
          a: ({ children, href }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-copper underline-offset-2 hover:underline"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-outside ml-6 mb-3 space-y-1">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-outside ml-6 mb-3 space-y-1">{children}</ol>
          ),
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          code: ({ children, className: cls }) => {
            const isBlock = cls?.includes("language-");
            if (isBlock) {
              return (
                <code className="font-mono text-sm">{children}</code>
              );
            }
            return (
              <code className="font-mono text-[0.875em] px-1 py-0.5 rounded bg-muted border border-border text-ink">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="bg-muted border-[1.5px] border-border-bold rounded-md p-4 mb-3 overflow-x-auto custom-scrollbar">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-[3px] border-amber pl-4 italic text-ink-soft my-4">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto custom-scrollbar mb-4">
              <table className="w-full border-[1.5px] border-border-bold rounded-md overflow-hidden">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-muted">{children}</thead>,
          th: ({ children }) => (
            <th className="text-left text-xs font-medium uppercase tracking-wider text-ink-soft px-3 py-2 border-b border-border">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 text-sm border-b border-border">{children}</td>
          ),
          hr: () => <hr className="my-6 border-border" />,
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">{children}</strong>
          ),
          em: ({ children }) => <em className="italic">{children}</em>,
        }}
      >
        {body}
      </ReactMarkdown>
      </div>
      {hasSources && (
        <aside
          aria-label="Sources cited by the agent"
          className="w-64 shrink-0 rounded-lg border-[1.5px] border-border-bold bg-card p-3 sticky top-4"
        >
          <p className="text-xs uppercase tracking-wider text-ink-soft inline-flex items-center gap-1.5 mb-2">
            <BookOpen className="h-3 w-3" aria-hidden="true" />
            Sources
            <span className="ml-auto font-mono text-foreground">{sources.length}</span>
          </p>
          <ul className="space-y-2">
            {sources.map((src, i) => (
              <li key={`${src.path}-${i}`} className="text-xs leading-relaxed">
                <p className="font-mono text-foreground break-all">{src.path}</p>
                {src.commitSha && (
                  <p className="font-mono text-ink-soft mt-0.5">@{src.commitSha.slice(0, 7)}</p>
                )}
                {src.relevance && (
                  <p className="text-ink-soft mt-0.5 italic">{src.relevance}</p>
                )}
              </li>
            ))}
          </ul>
        </aside>
      )}
    </div>
  );
}
