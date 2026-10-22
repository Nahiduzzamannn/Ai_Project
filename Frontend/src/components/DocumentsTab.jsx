import { useEffect, useState } from "react";
import { api } from "../api";
import { Alert, Badge, Button, Card, Field } from "./ui";
import { inputClass } from "./constants";

const SOURCE_LABELS = {
  toc: "from bookmarks",
  heading: "from headings",
  manual: "manual",
  full: "whole document",
};

export default function DocumentsTab({ documents, onChanged }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [openDoc, setOpenDoc] = useState(null);

  async function handleUpload(e) {
    e.preventDefault();
    setErr("");
    setMsg("");
    if (!file) return setErr("Please select a PDF file first.");
    if (!file.name.toLowerCase().endsWith(".pdf")) return setErr("Only PDF files are allowed.");
    try {
      setLoading(true);
      const doc = await api.uploadDocument(file);
      setMsg(`Uploaded "${doc.title}". Chapters detected and indexed.`);
      setFile(null);
      e.target.reset();
      await onChanged();
      setOpenDoc(doc.id);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card
        title="Upload a PDF"
        subtitle="The PDF is split into chapters and chunks, embedded into pgvector and indexed in Elasticsearch"
      >
        <form onSubmit={handleUpload} className="flex flex-col sm:flex-row gap-3 sm:items-center">
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="flex-1 block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 file:cursor-pointer border-2 border-dashed border-gray-300 rounded-lg p-3 hover:border-blue-400 transition-colors"
          />
          <Button type="submit" loading={loading} disabled={!file}>
            {loading ? "Processing..." : "Upload PDF"}
          </Button>
        </form>
        <div className="mt-4 space-y-2">
          <Alert onClose={() => setErr("")}>{err}</Alert>
          <Alert kind="success" onClose={() => setMsg("")}>{msg}</Alert>
        </div>
      </Card>

      <Card title="Uploaded documents" subtitle="Click a document to see and edit its chapters">
        {documents.length === 0 ? (
          <p className="text-gray-500 text-sm">No documents yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {documents.map((d) => (
              <DocumentRow
                key={d.id}
                doc={d}
                open={openDoc === d.id}
                onToggle={() => setOpenDoc(openDoc === d.id ? null : d.id)}
                onChanged={onChanged}
              />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function DocumentRow({ doc, open, onToggle, onChanged }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");

  async function run(name, fn) {
    setErr("");
    setBusy(name);
    try {
      await fn();
      await onChanged();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <button onClick={onToggle} className="flex-1 min-w-0 text-left">
          <span className="text-gray-400 mr-2">{open ? "▾" : "▸"}</span>
          <span className="font-medium text-gray-900 break-all">{doc.title}</span>
          <span className="ml-3 text-xs text-gray-500">
            #{doc.id} · {doc.chapter_count} chapters · {new Date(doc.created_at).toLocaleString()}
          </span>
        </button>
        <Badge color={doc.status === "PROCESSED" ? "green" : doc.status === "FAILED" ? "red" : "amber"}>
          {doc.status}
        </Badge>
        <Button
          variant="secondary"
          loading={busy === "reindex"}
          onClick={() => run("reindex", () => api.reindexDocument(doc.id))}
          title="Re-embed and re-index this PDF"
        >
          Re-index
        </Button>
        <Button
          variant="danger"
          loading={busy === "delete"}
          onClick={() =>
            confirm(`Delete "${doc.title}" and its chapters?`) &&
            run("delete", () => api.deleteDocument(doc.id))
          }
        >
          Delete
        </Button>
      </div>
      {err && <div className="mt-2"><Alert onClose={() => setErr("")}>{err}</Alert></div>}
      {open && <ChapterList docId={doc.id} onChanged={onChanged} />}
    </li>
  );
}

function ChapterList({ docId, onChanged }) {
  const [chapters, setChapters] = useState(null);
  const [form, setForm] = useState({ title: "", start_page: "", end_page: "" });
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    try {
      setChapters(await api.listChapters(docId));
    } catch (e) {
      setErr(e.message);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docId]);

  async function addChapter(e) {
    e.preventDefault();
    setErr("");
    setSaving(true);
    try {
      await api.createChapter(docId, {
        title: form.title,
        start_page: Number(form.start_page),
        end_page: Number(form.end_page),
      });
      setForm({ title: "", start_page: "", end_page: "" });
      await load();
      onChanged();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id) {
    try {
      await api.deleteChapter(id);
      await load();
      onChanged();
    } catch (e) {
      setErr(e.message);
    }
  }

  return (
    <div className="mt-3 ml-6 bg-gray-50 rounded-xl p-4 space-y-3">
      {chapters === null ? (
        <p className="text-sm text-gray-500">Loading chapters...</p>
      ) : chapters.length === 0 ? (
        <p className="text-sm text-gray-500">No chapters found.</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-500">
              <th className="pb-1">Chapter</th>
              <th className="pb-1 w-24">Pages</th>
              <th className="pb-1 w-32">Found</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody>
            {chapters.map((c) => (
              <tr key={c.id} className="border-t border-gray-200">
                <td className="py-1.5 pr-2">{c.title}</td>
                <td className="py-1.5">{c.start_page}–{c.end_page}</td>
                <td className="py-1.5 text-gray-500">{SOURCE_LABELS[c.source] || c.source}</td>
                <td className="py-1.5 text-right">
                  <button
                    onClick={() => confirm(`Delete chapter "${c.title}"?`) && remove(c.id)}
                    className="text-red-500 hover:text-red-700"
                    title="Delete chapter"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <form onSubmit={addChapter} className="flex flex-wrap gap-2 items-end pt-2 border-t border-gray-200">
        <Field label="Add chapter manually" className="flex-1 min-w-48">
          <input
            className={inputClass}
            placeholder="Chapter title"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            required
          />
        </Field>
        <Field label="From page" className="w-24">
          <input
            type="number"
            min="1"
            className={inputClass}
            value={form.start_page}
            onChange={(e) => setForm({ ...form, start_page: e.target.value })}
            required
          />
        </Field>
        <Field label="To page" className="w-24">
          <input
            type="number"
            min="1"
            className={inputClass}
            value={form.end_page}
            onChange={(e) => setForm({ ...form, end_page: e.target.value })}
            required
          />
        </Field>
        <Button type="submit" variant="secondary" loading={saving}>Add</Button>
      </form>
      <Alert onClose={() => setErr("")}>{err}</Alert>
    </div>
  );
}
