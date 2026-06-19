import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const TOOL_PATTERN = /🔧 \*\*Using ([^\*]+)\*\*\(([^)]*)\)\s*/g;

export function splitToolCalls(text) {
  const parts = [];
  let lastIndex = 0;
  let match;

  const regex = new RegExp(TOOL_PATTERN.source, "g");
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: "text", content: text.slice(lastIndex, match.index) });
    }
    parts.push({
      type: "tool",
      name: match[1].trim(),
      args: match[2].trim(),
    });
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < text.length) {
    parts.push({ type: "text", content: text.slice(lastIndex) });
  }

  return parts.length ? parts : [{ type: "text", content: text }];
}

export default function MarkdownContent({ content }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        h1: ({ children }) => <h1 className="md-h1">{children}</h1>,
        h2: ({ children }) => <h2 className="md-h2">{children}</h2>,
        h3: ({ children }) => <h3 className="md-h3">{children}</h3>,
        p: ({ children }) => <p className="md-p">{children}</p>,
        ul: ({ children }) => <ul className="md-ul">{children}</ul>,
        ol: ({ children }) => <ol className="md-ol">{children}</ol>,
        li: ({ children }) => <li className="md-li">{children}</li>,
        strong: ({ children }) => <strong className="md-strong">{children}</strong>,
        em: ({ children }) => <em className="md-em">{children}</em>,
        code: ({ inline, children }) =>
          inline ? (
            <code className="md-code-inline">{children}</code>
          ) : (
            <code className="md-code-block">{children}</code>
          ),
        pre: ({ children }) => <pre className="md-pre">{children}</pre>,
        blockquote: ({ children }) => <blockquote className="md-blockquote">{children}</blockquote>,
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="md-link">
            {children}
          </a>
        ),
        hr: () => <hr className="md-hr" />,
        table: ({ children }) => (
          <div className="md-table-wrap">
            <table className="md-table">{children}</table>
          </div>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
