import { useEffect, useState } from "react";
import { api } from "../api";
import { Alert, Badge, Button, Card, Field, QuestionView } from "./ui";
import { QTYPE_LABELS, inputClass } from "./constants";

const EMPTY = {
  text: "",
  qtype: "mcq",
  options: ["", "", "", ""],
  answer: "",
  marks: 1,
  difficulty: "medium",
  topic: "",
};
const SOURCE_COLORS = { manual: "gray", upload: "amber", ai: "purple" };
const PAGE_SIZE = 25;

export default function QuestionBankTab({ documents, selectedIds, setSelectedIds, onMakePaper }) {
  const [filters, setFilters] = useState({ q: "", qtype: "", topic: "", difficulty: "", source: "", document_id: "" });
  const [page, setPage] = useState(0);
  const [data, setData] = useState({ total: 0, items: [] });
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [editing, setEditing] = useState(null); // question being edited, or null for new

  async function load(p = page) {
    setLoading(true);
    setErr("");
    try {
      const [res, t] = await Promise.all([
        api.listQuestions({ ...filters, limit: PAGE_SIZE, offset: p * PAGE_SIZE }),
        api.listTopics(),
      ]);
      setData(res);
      setTopics(t);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page]);

  function applyFilters(e) {
    e?.preventDefault();
    setPage(0);
    load(0);
  }

  async function remove(id) {
    if (!confirm("Delete this question?")) return;
    try {
      await api.deleteQuestion(id);
      setSelectedIds(selectedIds.filter((x) => x !== id));
      load();
    } catch (e) {
      setErr(e.message);
    }
  }

  const selected = new Set(selectedIds);
  function toggle(id) {
    setSelectedIds(selected.has(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]);
  }
  const pageIds = data.items.map((q) => q.id);
  const allOnPage = pageIds.length > 0 && pageIds.every((id) => selected.has(id));
  function toggleAllOnPage() {
    if (allOnPage) setSelectedIds(selectedIds.filter((id) => !pageIds.includes(id)));
    else setSelectedIds([...selectedIds, ...pageIds.filter((id) => !selected.has(id))]);
  }

  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const setF = (k) => (e) => setFilters({ ...filters, [k]: e.target.value });

  return (
    <div className="space-y-6">
      <div className="grid lg:grid-cols-2 gap-6">
        <QuestionForm
          key={editing?.id ?? "new"}
          initial={editing}
          topics={topics}
          onCancel={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
        <UploadCard onUploaded={() => applyFilters()} />
      </div>

      <Card
        title={`Question bank (${data.total})`}
        subtitle="Search with Elasticsearch, filter, and tick questions to use in a question paper"
        actions={
          selectedIds.length > 0 && (
            <div className="flex gap-2">
              <Button variant="secondary" onClick={() => setSelectedIds([])}>Clear selection</Button>
              <Button variant="secondary" onClick={onMakePaper}>
                Make paper from {selectedIds.length} selected →
              </Button>
            </div>
          )
        }
      >
        <form onSubmit={applyFilters} className="grid grid-cols-2 md:grid-cols-7 gap-2 mb-4">
          <input
            className={`${inputClass} col-span-2`}
            placeholder="Search questions..."
            value={filters.q}
            onChange={setF("q")}
          />
          <select className={inputClass} value={filters.qtype} onChange={setF("qtype")}>
            <option value="">All types</option>
            {Object.entries(QTYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <select className={inputClass} value={filters.topic} onChange={setF("topic")}>
            <option value="">All topics</option>
            {topics.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className={inputClass} value={filters.difficulty} onChange={setF("difficulty")}>
            <option value="">Any difficulty</option>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
            <option value="mixed">Mixed</option>
          </select>
          <select className={inputClass} value={filters.source} onChange={setF("source")}>
            <option value="">Any source</option>
            <option value="manual">Manual</option>
            <option value="upload">Uploaded</option>
            <option value="ai">AI generated</option>
          </select>
          <Button type="submit" loading={loading}>Filter</Button>
        </form>
        {documents.length > 0 && (
          <div className="mb-4 max-w-sm">
            <select className={inputClass} value={filters.document_id} onChange={setF("document_id")}>
              <option value="">From any document</option>
              {documents.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
            </select>
          </div>
        )}
        <Alert onClose={() => setErr("")}>{err}</Alert>

        {data.items.length === 0 ? (
          <p className="text-sm text-gray-500">No questions found.</p>
        ) : (
          <>
            <label className="flex items-center gap-2 text-sm text-gray-600 mb-2">
              <input type="checkbox" checked={allOnPage} onChange={toggleAllOnPage} className="h-4 w-4 accent-purple-600" />
              Select all on this page
            </label>
            <ul className="space-y-2">
              {data.items.map((q) => (
                <li
                  key={q.id}
                  className={`flex gap-3 p-3 rounded-lg border ${selected.has(q.id) ? "border-purple-300 bg-purple-50" : "border-gray-200"}`}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(q.id)}
                    onChange={() => toggle(q.id)}
                    className="mt-1 h-4 w-4 accent-purple-600"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap gap-1.5 mb-1">
                      <span className="text-xs text-gray-400">#{q.id}</span>
                      <Badge color="blue">{QTYPE_LABELS[q.qtype]}</Badge>
                      <Badge>{q.marks} marks</Badge>
                      <Badge>{q.difficulty}</Badge>
                      <Badge color={SOURCE_COLORS[q.source]}>{q.source}</Badge>
                      {q.topic && <Badge color="green">{q.topic}</Badge>}
                    </div>
                    <QuestionView q={q} />
                  </div>
                  <div className="flex flex-col gap-1 text-sm">
                    <button
                      className="text-blue-600 hover:underline"
                      onClick={() => {
                        setEditing(q);
                        window.scrollTo({ top: 0, behavior: "smooth" });
                      }}
                    >
                      Edit
                    </button>
                    <button className="text-red-600 hover:underline" onClick={() => remove(q.id)}>
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between mt-4 text-sm">
              <Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>← Prev</Button>
              <span className="text-gray-500">Page {page + 1} of {pages}</span>
              <Button variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next →</Button>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}

function QuestionForm({ initial, topics, onSaved, onCancel }) {
  const [form, setForm] = useState(() =>
    initial
      ? {
          ...EMPTY,
          ...initial,
          options: initial.qtype === "mcq" ? [...(initial.options || [])] : EMPTY.options,
          answer: initial.answer || "",
          topic: initial.topic || "",
        }
      : EMPTY
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  function setQtype(qtype) {
    const marks = { mcq: 1, true_false: 1, short: 2, broad: 5 }[qtype];
    setForm({ ...form, qtype, marks, answer: qtype === "true_false" ? "True" : "" });
  }

  function setOption(i, value) {
    const options = [...form.options];
    const wasAnswer = form.answer === options[i];
    options[i] = value;
    setForm({ ...form, options, answer: wasAnswer ? value : form.answer });
  }

  async function submit(e) {
    e.preventDefault();
    setErr("");
    setMsg("");
    const body = {
      text: form.text.trim(),
      qtype: form.qtype,
      options: form.qtype === "mcq" ? form.options.filter((o) => o.trim()) : null,
      answer: form.answer || null,
      marks: Number(form.marks),
      difficulty: form.difficulty,
      topic: form.topic.trim() || null,
      document_id: initial?.document_id ?? null,
      chapter_id: initial?.chapter_id ?? null,
    };
    setSaving(true);
    try {
      if (initial) await api.updateQuestion(initial.id, body);
      else await api.createQuestion(body);
      if (!initial) {
        setForm({ ...EMPTY, qtype: form.qtype, marks: form.marks, difficulty: form.difficulty, topic: form.topic });
        setMsg("Question added.");
      }
      onSaved();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title={initial ? `Edit question #${initial.id}` : "Add a question"}>
      <form onSubmit={submit} className="space-y-3">
        <div className="flex flex-wrap gap-2">
          {Object.entries(QTYPE_LABELS).map(([k, v]) => (
            <button
              type="button"
              key={k}
              onClick={() => setQtype(k)}
              className={`px-3 py-1 rounded-full text-sm border ${form.qtype === k ? "bg-purple-600 text-white border-purple-600" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`}
            >
              {v}
            </button>
          ))}
        </div>
        <Field label="Question">
          <textarea className={inputClass} rows={2} value={form.text} onChange={set("text")} required />
        </Field>

        {form.qtype === "mcq" && (
          <div className="space-y-1.5">
            <span className="block text-xs font-medium text-gray-600">Options (select the correct one)</span>
            {form.options.map((o, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="correct"
                  checked={!!o && form.answer === o}
                  onChange={() => setForm({ ...form, answer: o })}
                  className="accent-green-600"
                  title="Correct answer"
                />
                <span className="text-sm text-gray-500 w-5">{"abcdefgh"[i]})</span>
                <input className={inputClass} value={o} onChange={(e) => setOption(i, e.target.value)} />
              </div>
            ))}
            {form.options.length < 8 && (
              <button type="button" className="text-sm text-blue-600 hover:underline" onClick={() => setForm({ ...form, options: [...form.options, ""] })}>
                + Add option
              </button>
            )}
          </div>
        )}
        {form.qtype === "true_false" && (
          <Field label="Answer">
            <select className={inputClass} value={form.answer} onChange={set("answer")}>
              <option>True</option>
              <option>False</option>
            </select>
          </Field>
        )}
        {(form.qtype === "short" || form.qtype === "broad") && (
          <Field label="Answer (optional, used in the answer key)">
            <textarea className={inputClass} rows={2} value={form.answer} onChange={set("answer")} />
          </Field>
        )}

        <div className="grid grid-cols-3 gap-2">
          <Field label="Marks">
            <input type="number" min="0.5" step="0.5" className={inputClass} value={form.marks} onChange={set("marks")} />
          </Field>
          <Field label="Difficulty">
            <select className={inputClass} value={form.difficulty} onChange={set("difficulty")}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </Field>
          <Field label="Topic / chapter">
            <input className={inputClass} list="topic-list" value={form.topic} onChange={set("topic")} />
            <datalist id="topic-list">
              {topics.map((t) => <option key={t} value={t} />)}
            </datalist>
          </Field>
        </div>
        <div className="flex gap-2">
          <Button type="submit" loading={saving} className="flex-1">{initial ? "Save changes" : "Add to bank"}</Button>
          {initial && <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>}
        </div>
        <Alert onClose={() => setErr("")}>{err}</Alert>
        <Alert kind="success" onClose={() => setMsg("")}>{msg}</Alert>
      </form>
    </Card>
  );
}

function UploadCard({ onUploaded }) {
  const [file, setFile] = useState(null);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);

  async function upload(e) {
    e.preventDefault();
    setErr("");
    setResult(null);
    setLoading(true);
    try {
      const res = await api.uploadQuestions(file, topic);
      setResult(res);
      e.target.reset();
      setFile(null);
      onUploaded();
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title="Upload questions" subtitle="Bulk import from a CSV or JSON file">
      <form onSubmit={upload} className="space-y-3">
        <input
          type="file"
          accept=".csv,.json"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 file:cursor-pointer border-2 border-dashed border-gray-300 rounded-lg p-3"
        />
        <Field label="Default topic for rows without one (optional)">
          <input className={inputClass} value={topic} onChange={(e) => setTopic(e.target.value)} />
        </Field>
        <Button type="submit" loading={loading} disabled={!file} className="w-full">Upload</Button>
      </form>
      <div className="mt-3 space-y-2">
        <Alert onClose={() => setErr("")}>{err}</Alert>
        {result && (
          <Alert kind={result.failed ? "info" : "success"} onClose={() => setResult(null)}>
            {`Imported ${result.imported} question(s).`}
            {result.failed > 0 &&
              `\n${result.failed} row(s) skipped:\n` +
                result.errors.map((e) => `Row ${e.row}: ${e.error}`).join("\n")}
          </Alert>
        )}
      </div>
      <div className="mt-4 text-xs text-gray-500 space-y-1">
        <p>
          CSV columns: <code>text, qtype, options, answer, marks, difficulty, topic</code>. Separate MCQ
          options with <code>|</code>. qtype is one of <code>mcq, true_false, short, broad</code>.
        </p>
        <a href={api.templateUrl} className="text-blue-600 hover:underline">Download CSV template</a>
      </div>
    </Card>
  );
}
