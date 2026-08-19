import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, AssistantAnswer } from "../api";

/** One exchange. Kept in page state only — an assistant question is a lookup,
 *  not a case record, so there is nothing to persist between visits. The audit
 *  trail on the server is the durable record of what was asked. */
type Exchange = {
  id: number;
  question: string;
  answer?: AssistantAnswer;
  error?: string;
};

/** Openers that show what the surface is for without the reviewer having to
 *  guess: a safety profile, an interaction, a population, a signal question. */
const EXAMPLES = [
  "What adverse reactions are reported with mupirocin in neonates?",
  "Is there evidence linking fusidic acid to hepatotoxicity?",
  "What is known about zinc supplementation and copper deficiency?",
  "Has centhaquine been studied in hypovolaemic shock?",
];

/** Render an answer, turning the model's [n] citations into links to the source
 *  list. The regex is deliberately narrow — only bracketed digits become links,
 *  so ordinary bracketed prose is left alone. */
function AnswerBody({
  answer,
  turnId,
}: {
  answer: AssistantAnswer;
  turnId: number;
}) {
  const byNumber = new Map(answer.sources.map((s) => [s.number, s]));
  return (
    <div className="chat-answer">
      {answer.answer.split("\n").map((paragraph, index) => {
        if (!paragraph.trim()) return null;
        const pieces = paragraph.split(/(\[\d+\])/g);
        return (
          <p key={index}>
            {pieces.map((piece, pieceIndex) => {
              const match = /^\[(\d+)\]$/.exec(piece);
              if (!match) return <span key={pieceIndex}>{piece}</span>;
              const source = byNumber.get(Number(match[1]));
              if (!source) return <span key={pieceIndex}>{piece}</span>;
              return (
                <a
                  key={pieceIndex}
                  className="cite"
                  href={`#source-${turnId}-${source.number}`}
                  title={source.title}
                >
                  {match[1]}
                </a>
              );
            })}
          </p>
        );
      })}
    </div>
  );
}

export default function ChatPage() {
  const [question, setQuestion] = useState("");
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [exchanges, busy]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 3 || busy) return;
    const id = Date.now();
    setExchanges((current) => [...current, { id, question: trimmed }]);
    setQuestion("");
    setBusy(true);
    try {
      const answer = await api.assistantAsk(trimmed);
      setExchanges((current) =>
        current.map((x) => (x.id === id ? { ...x, answer } : x)),
      );
    } catch (caught) {
      setExchanges((current) =>
        current.map((x) =>
          x.id === id ? { ...x, error: String(caught) } : x,
        ),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="shd">
        <span className="eyebrow">Literature assistant</span>
        <h1>Ask the literature</h1>
        <p className="sub">
          A free-text question instead of a product and a search string. Answers
          are written only from the PubMed abstracts cited beneath them, so every
          claim can be traced to a paper.
        </p>
      </div>

      <div className="banner" style={{ marginBottom: "1.1rem" }}>
        <div>
          <b>This is a lookup, not a determination</b>
          Nothing asked here is recorded against a case, and no answer is a
          clinical or regulatory decision. Case assessment stays in the review
          workflow. Questions are written to the audit trail.
        </div>
      </div>

      <div className="chat">
        {exchanges.length === 0 ? (
          <div className="chat-empty">
            <p className="muted">
              Ask about a molecule, an event, a population, or anything else the
              published literature would answer.
            </p>
            <div className="chat-examples">
              {EXAMPLES.map((example) => (
                <button
                  key={example}
                  className="chat-example"
                  onClick={() => ask(example)}
                  disabled={busy}
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="chat-thread">
            {exchanges.map((exchange) => (
              <article className="chat-turn" key={exchange.id}>
                <div className="chat-question">
                  <span className="lbl">Question</span>
                  <p>{exchange.question}</p>
                </div>

                {exchange.error ? (
                  <div className="error">{exchange.error}</div>
                ) : !exchange.answer ? (
                  <p className="muted chat-thinking">
                    Searching PubMed and reading abstracts…
                  </p>
                ) : (
                  <>
                    {exchange.answer.warning ? (
                      <div className="warn-banner">{exchange.answer.warning}</div>
                    ) : null}

                    <AnswerBody answer={exchange.answer} turnId={exchange.id} />

                    <div className="chat-meta">
                      <span className="pill mono">
                        {exchange.answer.total_matches.toLocaleString()} PubMed
                        matches
                      </span>
                      <span className="pill mono">
                        {exchange.answer.sources.length} cited
                      </span>
                      {exchange.answer.synthesised ? (
                        <span className="pill acc mono">
                          {exchange.answer.model_id}
                        </span>
                      ) : (
                        <span className="pill warn mono">retrieval only</span>
                      )}
                    </div>

                    <details className="chat-query">
                      <summary>Search that produced these sources</summary>
                      <pre className="report-query">
                        {exchange.answer.pubmed_query}
                      </pre>
                    </details>

                    {exchange.answer.sources.length > 0 ? (
                      <div className="chat-sources">
                        <span className="lbl">Sources</span>
                        <ol>
                          {exchange.answer.sources.map((source) => (
                            <li
                              key={source.pmid}
                              id={`source-${exchange.id}-${source.number}`}
                            >
                              <a
                                href={source.url}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {source.title}
                              </a>
                              <span className="src">
                                {source.journal || "Journal not stated"}
                                {source.pub_date ? ` · ${source.pub_date}` : ""}
                                {" · PMID "}
                                {source.pmid}
                              </span>
                              {source.article_id ? (
                                <Link
                                  className="pill acc"
                                  to={`/articles/${source.article_id}`}
                                >
                                  Monitored — open report
                                </Link>
                              ) : null}
                            </li>
                          ))}
                        </ol>
                      </div>
                    ) : null}
                  </>
                )}
              </article>
            ))}
          </div>
        )}

        <form
          className="chat-composer no-print"
          onSubmit={(event) => {
            event.preventDefault();
            ask(question);
          }}
        >
          <textarea
            aria-label="Your question"
            rows={2}
            value={question}
            placeholder="Ask anything the published literature would answer…"
            onChange={(event) => setQuestion(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends; Shift+Enter is a newline, as in any chat box.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                ask(question);
              }
            }}
          />
          <div className="chat-composer-actions">
            <button
              className="btn primary"
              type="submit"
              disabled={busy || question.trim().length < 3}
            >
              {busy ? "Searching…" : "Ask"}
            </button>
            {exchanges.length > 0 ? (
              <button
                className="btn ghost"
                type="button"
                onClick={() => setExchanges([])}
                disabled={busy}
              >
                Clear
              </button>
            ) : null}
          </div>
        </form>
      </div>

      <div ref={endRef} />
    </div>
  );
}
