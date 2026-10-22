import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { api } from "../api";
import { Alert, Badge, Button, Card, QuestionView, Spinner } from "./ui";
import { QTYPE_LABELS, inputClass } from "./constants";

const STORAGE_KEY = "rag-chat-v1";
const SUGGESTIONS = [
  "Summarize this chapter in 5 bullet points",
  "Give me 5 MCQ from this chapter",
  "Make 3 short and 2 broad questions",
  "Write 5 true/false questions",
  "Make the questions harder",
  "এই অধ্যায় থেকে ৫টি MCQ দাও",
];

function loadSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export default function ChatTab({ documents, onNeedKey }) {
  const saved = loadSaved();
  // scope: { documentId, chapter: {id, title, start_page, end_page} | null }
  const [scope, setScope] = useState(saved?.scope || { documentId: "", chapter: null });
  const [messages, setMessages] = useState(saved?.messages || []);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState("");
  const bottomRef = useRef(null);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ scope, messages }));
    } catch {
      /* storage unavailable: chat just won't survive a reload */
    }
  }, [scope, messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  function changeScope(next) {
    if (messages.length && !confirm("Changing the scope starts a new chat. Continue?")) return;
    setScope(next);
    setMessages([]);
    setErr("");
  }

  async function send(text) {
    const content = (text ?? input).trim();
    if (!content || sending) return;
    setErr("");
    setInput("");
    const next = [...messages, { role: "user", content }];
    setMessages(next);
    setSending(true);
    try {
      const res = await api.chat({
        messages: next.map(({ role, content, questions }) => ({ role, content, questions })),
        chapter_id: scope.chapter?.id ?? null,
        document_id: scope.documentId ? Number(scope.documentId) : null,
      });
      setMessages([
        ...next,
        { role: "assistant", content: res.reply, questions: res.questions, sources: res.sources },
      ]);
    } catch (e) {
      setErr(e.message);
      // Put the text back so the user can retry
      setMessages(messages);
      setInput(content);
    } finally {
      setSending(false);
    }
  }

  function updateMessage(i, patch) {
    setMessages((ms) => ms.map((m, idx) => (idx === i ? { ...m, ...patch } : m)));
  }

  const scopeLabel = scope.chapter
    ? `${scope.chapter.title} (pages ${scope.chapter.start_page}–${scope.chapter.end_page})`
    : scope.documentId
      ? documents.find((d) => String(d.id) === String(scope.documentId))?.title || "Document"
      : "All documents";

  return (
    <div className="grid lg:grid-cols-3 gap-6">
      <div className="lg:col-span-1">
        <ScopePicker documents={documents} scope={scope} onChange={changeScope} />
      </div>

      <div className="lg:col-span-2">
        <section className="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden flex flex-col h-[78vh] min-h-[480px]">
          <div className="bg-linear-to-r from-blue-500 to-purple-600 px-5 py-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <h2 className="text-lg font-semibold text-white">AI Question Chat</h2>
              <p className="text-blue-50 text-xs truncate">Talking about: {scopeLabel}</p>
            </div>
            {messages.length > 0 && (
              <button
                onClick={() => confirm("Start a new chat?") && (setMessages([]), setErr(""))}
                className="text-sm text-white border border-white/50 rounded-lg px-3 py-1 hover:bg-white/10 shrink-0"
              >
                New chat
              </button>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
            {messages.length === 0 && (
              <div className="text-center text-gray-500 text-sm mt-8 space-y-4">
                <p>
                  Ask anything about <b>{scopeLabel}</b>, or ask for questions.
                  <br />
                  Each message searches the PDF (pgvector + Elasticsearch) and the AI answers from what it finds.
                </p>
                <div className="flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="px-3 py-1.5 rounded-full border border-purple-200 bg-white text-purple-700 hover:bg-purple-50"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] bg-linear-to-r from-blue-500 to-purple-600 text-white rounded-2xl rounded-br-sm px-4 py-2 whitespace-pre-wrap">
                    {m.content}
                  </div>
                </div>
              ) : (
                <AssistantMessage key={i} message={m} onUpdate={(patch) => updateMessage(i, patch)} />
              )
            )}

            {sending && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <Spinner /> Searching the PDF and thinking...
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="border-t border-gray-200 p-3 bg-white">
            {err && err.includes("LLM_API_KEY") ? (
              <div className="mb-2 flex items-center justify-between gap-3 bg-amber-50 border-l-4 border-amber-500 p-3 rounded-lg text-sm text-amber-900">
                <span>The AI isn't connected yet. Add a free API key to start chatting.</span>
                <Button type="button" onClick={onNeedKey}>Set AI key</Button>
              </div>
            ) : (
              err && <div className="mb-2"><Alert onClose={() => setErr("")}>{err}</Alert></div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send();
              }}
              className="flex gap-2 items-end"
            >
              <textarea
                rows={2}
                className={`${inputClass} resize-none`}
                placeholder="e.g. Give me 5 MCQ on the Calvin cycle   (Enter to send, Shift+Enter for new line)"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
              />
              <Button type="submit" loading={sending} disabled={!input.trim()}>Send</Button>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}

function AssistantMessage({ message, onUpdate }) {
  const questions = message.questions || [];
  const [picked, setPicked] = useState(() => new Set(questions.map((_, i) => i).filter((i) => !message.savedIdx?.includes(i))));
  const [showSources, setShowSources] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const savedIdx = new Set(message.savedIdx || []);

  function toggle(i) {
    const next = new Set(picked);
    next.has(i) ? next.delete(i) : next.add(i);
    setPicked(next);
  }

  async function save() {
    setErr("");
    setSaving(true);
    try {
      const idx = [...picked].filter((i) => !savedIdx.has(i));
      await api.createQuestions(idx.map((i) => questions[i]));
      onUpdate({ savedIdx: [...savedIdx, ...idx] });
      setPicked(new Set());
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  const unsavedPicked = [...picked].filter((i) => !savedIdx.has(i)).length;

  return (
    <div className="flex">
      <div className="max-w-[95%] w-full bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
        <div className="prose-chat text-sm text-gray-800">
          <Markdown>{message.content}</Markdown>
        </div>

        {questions.length > 0 && (
          <div className="mt-3 border-t border-gray-100 pt-3">
            <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
              <span className="text-sm font-semibold text-gray-700">{questions.length} question(s)</span>
              <Button variant="secondary" loading={saving} disabled={unsavedPicked === 0} onClick={save}>
                Save {unsavedPicked} to bank
              </Button>
            </div>
            <ul className="space-y-2">
              {questions.map((q, i) => (
                <li key={i} className={`flex gap-3 p-2.5 rounded-lg border ${savedIdx.has(i) ? "border-green-200 bg-green-50" : "border-gray-200"}`}>
                  {savedIdx.has(i) ? (
                    <span className="text-green-600 text-sm mt-0.5" title="Saved to bank">✓</span>
                  ) : (
                    <input
                      type="checkbox"
                      checked={picked.has(i)}
                      onChange={() => toggle(i)}
                      className="mt-1 h-4 w-4 accent-purple-600"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap gap-1.5 mb-1">
                      <span className="text-xs text-gray-400">Q{i + 1}</span>
                      <Badge color="blue">{QTYPE_LABELS[q.qtype]}</Badge>
                      <Badge>{q.marks} marks</Badge>
                      <Badge>{q.difficulty}</Badge>
                      {savedIdx.has(i) && <Badge color="green">saved</Badge>}
                    </div>
                    <QuestionView q={q} />
                  </div>
                </li>
              ))}
            </ul>
            {err && <div className="mt-2"><Alert onClose={() => setErr("")}>{err}</Alert></div>}
          </div>
        )}

        {message.sources?.length > 0 && (
          <div className="mt-2">
            <button onClick={() => setShowSources(!showSources)} className="text-xs text-blue-600 hover:underline">
              {showSources ? "Hide" : "Show"} sources ({message.sources.length})
            </button>
            {showSources && (
              <ol className="mt-2 space-y-1.5">
                {message.sources.map((s) => (
                  <li key={s.n} className="text-xs text-gray-600 bg-gray-50 rounded p-2">
                    <span className="font-semibold">[{s.n}]</span> {s.document_title}, page {s.page_number}
                    <div className="text-gray-500 mt-0.5">{s.snippet}…</div>
                  </li>
                ))}
              </ol>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function ScopePicker({ documents, scope, onChange }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState(null);
  const [chapters, setChapters] = useState([]);
  const [searching, setSearching] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!scope.documentId) return;
    let alive = true;
    api.listChapters(scope.documentId)
      .then((c) => alive && setChapters(c))
      .catch(() => alive && setChapters([]));
    return () => {
      alive = false;
    };
  }, [scope.documentId]);

  async function search(e) {
    e.preventDefault();
    setErr("");
    setSearching(true);
    try {
      setResults(await api.searchChapters({ q, document_id: scope.documentId, top_k: 8 }));
    } catch (e) {
      setErr(e.message);
    } finally {
      setSearching(false);
    }
  }

  const pick = (ch) => onChange({ documentId: String(ch.document_id), chapter: ch });
  const chapterButton = (ch, extra) => (
    <button
      key={ch.id}
      onClick={() => pick(ch)}
      className={`w-full text-left p-2.5 rounded-lg border text-sm transition-colors ${
        scope.chapter?.id === ch.id ? "border-purple-400 bg-purple-50" : "border-gray-200 hover:border-blue-300 hover:bg-blue-50"
      }`}
    >
      <div className="font-medium text-gray-900">{ch.title}</div>
      <div className="text-xs text-gray-500">
        {extra ? `${extra} · ` : ""}pages {ch.start_page}–{ch.end_page}
      </div>
    </button>
  );

  return (
    <Card title="What to chat about" subtitle="Pick all documents, one PDF, or one chapter">
      <div className="space-y-4">
        <select
          className={inputClass}
          value={scope.documentId}
          onChange={(e) => onChange({ documentId: e.target.value, chapter: null })}
        >
          <option value="">All documents</option>
          {documents.map((d) => (
            <option key={d.id} value={d.id}>{d.title}</option>
          ))}
        </select>

        {scope.chapter && (
          <div className="flex items-center justify-between gap-2 text-sm bg-purple-50 border border-purple-200 rounded-lg p-2">
            <span className="min-w-0 truncate">Chapter: <b>{scope.chapter.title}</b></span>
            <button
              className="text-purple-700 hover:underline shrink-0"
              onClick={() => onChange({ documentId: scope.documentId, chapter: null })}
            >
              Whole PDF
            </button>
          </div>
        )}

        <form onSubmit={search} className="flex gap-2">
          <input
            className={inputClass}
            placeholder="Search a chapter..."
            value={q}
            onChange={(e) => setQ(e.target.value)}
            required
          />
          <Button type="submit" variant="secondary" loading={searching}>Find</Button>
        </form>
        <Alert onClose={() => setErr("")}>{err}</Alert>

        {results && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-gray-500">Search results</p>
            {results.length === 0 && <p className="text-sm text-gray-500">No chapters found.</p>}
            {results.map((r) => chapterButton(r, r.document_title))}
          </div>
        )}

        {scope.documentId && chapters.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-gray-500">Chapters in this PDF</p>
            <div className="max-h-72 overflow-y-auto space-y-2 pr-1">{chapters.map((c) => chapterButton(c))}</div>
          </div>
        )}
      </div>
    </Card>
  );
}
