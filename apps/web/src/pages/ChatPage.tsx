import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, AssistantAnswer, AssistantTurn } from "../api";

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
  "What adverse reactions are reported with mupirocin?",
  "Is there evidence linking fusidic acid to hepatotoxicity?",
  "What is known about zinc supplementation and copper deficiency?",
  "Has centhaquine been studied in hypovolaemic shock?",
];

/** Render an answer from its cited segments.
 *
 *  Citations are structured data from the API rather than markers the model
 *  wrote into prose, so each one is anchored to the span it supports and
 *  carries the sentence it quotes — the marker's tooltip is the evidence, not
 *  a restatement of the title.
 */
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
      <p>
        {answer.segments.map((segment, index) => (
          <span key={index}>
            {segment.text}
            {segment.citations.map((number, citationIndex) => {
              const source = byNumber.get(number);
              const quote = segment.quotes[citationIndex];
              return (
                <a
                  key={number}
                  className="cite"
                  href={`#source-${turnId}-${number}`}
                  title={
                    quote
                      ? `“${quote}”\n\n— ${source?.title ?? `source ${number}`}`
                      : source?.title
                  }
                >
                  {number}
                </a>
              );
            })}
          </span>
        ))}
      </p>
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
    // Prior turns let the server resolve a follow-up ("and in children?")
    // against what came before. Only answered turns are useful context.
    const history: AssistantTurn[] = exchanges
      .filter((x): x is Exchange & { answer: AssistantAnswer } => !!x.answer)
      .map((x) => ({ question: x.question, answer: x.answer.answer }));

    const id = Date.now();
    setExchanges((current) => [...current, { id, question: trimmed }]);
    setQuestion("");
    setBusy(true);
    try {
      const answer = await api.assistantAsk(trimmed, { history });
      setExchanges((current) =>
        current.map((x) => (x.id === id ? { ...x, answer } : x)),
      );
    } catch (caught) {
      setExchanges((current) =>
        current.map((x) => (x.id === id ? { ...x, error: String(caught) } : x)),
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
          are written only from the PubMed abstracts cited beneath them, and
          every citation quotes the sentence it came from.
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
              published literature would answer. Follow-up questions work — ask
              “and in neonates?” and it will carry the subject forward.
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
                  {exchange.answer &&
                  exchange.answer.interpreted_question !== exchange.question ? (
                    <span className="chat-interpreted">
                      Read as: {exchange.answer.interpreted_question}
                    </span>
                  ) : null}
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
                        {exchange.answer.sources.filter((s) => s.cited).length} of{" "}
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
                              className={source.cited ? "is-cited" : ""}
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
                              <span className="chat-source-tags">
                                {source.cited ? (
                                  <span className="pill ok">Cited</span>
                                ) : (
                                  <span className="pill">
                                    Retrieved, not cited
                                  </span>
                                )}
                                {source.article_id ? (
                                  <Link
                                    className="pill acc"
                                    to={`/articles/${source.article_id}`}
                                  >
                                    Monitored — open report
                                  </Link>
                                ) : null}
                              </span>
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
            placeholder={
              exchanges.length
                ? "Ask a follow-up — the subject carries forward…"
                : "Ask anything the published literature would answer…"
            }
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
                New conversation
              </button>
            ) : null}
            {exchanges.length > 0 ? (
              <span className="muted">
                {exchanges.length === 1
                  ? "Follow-ups use this turn for context."
                  : `Follow-ups use the ${Math.min(exchanges.length, 4)} most recent turns for context.`}
              </span>
            ) : null}
          </div>
        </form>
      </div>

      <div ref={endRef} />
    </div>
  );
}
