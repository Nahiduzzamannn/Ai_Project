import { useEffect, useState } from "react";
import { api } from "../api";
import { Alert, Button, Card, Field, RichText } from "./ui";
import { inputClass } from "./constants";

export default function OcrTab({ onSaved }) {
  const [file, setFile] = useState(null);
  const [subject, setSubject] = useState("বাংলা");
  const [imports, setImports] = useState([]);
  const [current, setCurrent] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const activeImportId = current?.id;
  const activeImportStatus = current?.status;

  useEffect(() => {
    api.listOcrImports().then((items) => {
      setImports(items);
      if (items.length > 0) {
        // Auto-select an active job if in-progress, or the most recent one
        const activeItem = items.find((it) => ["queued", "processing"].includes(it.status)) || items[0];
        if (activeItem) {
          api.getOcrImport(activeItem.id).then((row) => {
            showImport(row);
            if (row.status === "completed") {
              setMessage("OCR সম্পন্ন হয়েছে। নিচে প্রশ্নগুলো দেখে নিন।");
            } else if (["queued", "processing"].includes(row.status)) {
              setMessage(`OCR চলছে (${row.processed_pages}/${row.total_pages} পৃষ্ঠা)...`);
            }
          }).catch(() => {});
        }
      }
    }).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeImportId || !["queued", "processing"].includes(activeImportStatus)) return;
    let active = true;
    let timer;
    let controller;
    async function poll() {
      controller = new AbortController();
      try {
        const row = await api.getOcrImport(activeImportId, controller.signal);
        if (!active) return;
        setError("");

        // Keep "আগের স্ক্যান" buttons updated in real-time
        setImports((prev) =>
          prev.map((item) =>
            item.id === row.id
              ? { ...item, status: row.status, processed_pages: row.processed_pages, total_pages: row.total_pages }
              : item
          )
        );

        if (row.status === "completed") {
          showImport(row);
          setMessage("OCR সফলভাবে সম্পন্ন হয়েছে! নিচে প্রশ্নগুলো দেখে নিন এবং সংশোধন করুন।");
        } else if (row.status === "processing") {
          setCurrent(row);
          setMessage(`OCR চলছে (${row.processed_pages}/${row.total_pages} পৃষ্ঠা)... অনুগ্রহ করে অপেক্ষা করুন।`);
        } else if (row.status === "failed") {
          setCurrent(row);
          setMessage("");
          setError(row.error || "OCR ব্যর্থ হয়েছে।");
        } else {
          setCurrent(row);
        }

        if (!["queued", "processing"].includes(row.status)) {
          api.listOcrImports().then((items) => { if (active) setImports(items); }).catch(() => {});
          return;
        }
      } catch (err) {
        if (active && err.name !== "AbortError") setError(err.message);
      }
      if (active) timer = setTimeout(poll, 2000);
    }
    timer = setTimeout(poll, 2000);
    return () => { active = false; clearTimeout(timer); controller?.abort(); };
  }, [activeImportId, activeImportStatus]);

  function showImport(row) {
    setCurrent(row);
    setCandidates((row.candidates || []).map((q, i) => ({ ...q, key: i, selected: true, optionsText: (q.options || []).join("\n") })));
    setImports((prev) =>
      prev.map((item) =>
        item.id === row.id
          ? { ...item, status: row.status, processed_pages: row.processed_pages, total_pages: row.total_pages }
          : item
      )
    );
  }

  async function upload(e) {
    e.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      const row = await api.createOcrImport(file, subject.trim());
      showImport(row);
      setMessage("ফাইল গ্রহণ করা হয়েছে। OCR শুরু হওয়ার অপেক্ষায় আছে...");
      const updatedList = await api.listOcrImports();
      setImports(updatedList);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function openImport(id) {
    setError("");
    setMessage("");
    try {
      const row = await api.getOcrImport(id);
      showImport(row);
      if (row.status === "completed") {
        setMessage("OCR সম্পন্ন হয়েছে। নিচে প্রশ্নগুলো দেখে নিন।");
      } else if (["queued", "processing"].includes(row.status)) {
        setMessage(`OCR চলছে (${row.processed_pages}/${row.total_pages} পৃষ্ঠা)...`);
      }
    } catch (err) { setError(err.message); }
  }

  function update(key, field, value) {
    setCandidates((items) => items.map((q) => q.key === key ? { ...q, [field]: value } : q));
  }

  async function save() {
    const selected = candidates.filter((q) => q.selected);
    if (!selected.length) return setError("Save করার জন্য অন্তত একটি প্রশ্ন বেছে নিন।");
    const questions = selected.map((q) => ({
      text: q.text.trim(), qtype: q.qtype,
      options: q.qtype === "mcq" ? q.optionsText.split("\n").map((o) => o.trim()).filter(Boolean) : null,
      answer: null, marks: q.qtype === "mcq" ? 1 : 2,
      difficulty: "medium", topic: current.subject,
    }));
    setBusy(true); setError("");
    try {
      await api.acceptOcrQuestions(current.id, questions);
      onSaved();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return <div className="space-y-6">
    <Card title="ছবি বা PDF থেকে প্রশ্ন" subtitle="বাংলা ও ইংরেজি OCR; সংরক্ষণের আগে সব প্রশ্ন দেখে নিন">
      <form onSubmit={upload} className="grid md:grid-cols-[1fr_12rem_auto] gap-3 items-end">
        <Field label="Question image / PDF (20 MB, PDF সর্বোচ্চ 30 পৃষ্ঠা)">
          <input className={inputClass} type="file" accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff" onChange={(e) => setFile(e.target.files?.[0] || null)} required />
        </Field>
        <Field label="বিষয়"><input className={inputClass} value={subject} onChange={(e) => setSubject(e.target.value)} required /></Field>
        <Button type="submit" disabled={!file || !subject.trim()} loading={busy}>OCR করুন</Button>
      </form>
      <p className="text-xs text-gray-500 mt-3">পরিষ্কার, সোজা ছবি ভালো ফল দেয়। গণিতের সূত্র OCR-এ ভুল হতে পারে; $...$ দিয়ে LaTeX লিখে browser preview দেখুন।</p>
      <div className="mt-3 space-y-2">
        <Alert kind="error">{error}</Alert>
        {message && (
          <Alert kind={current?.status === "completed" ? "success" : "info"}>
            <div className="flex items-center gap-2">
              {["queued", "processing"].includes(current?.status) && (
                <span className="inline-block w-2.5 h-2.5 rounded-full bg-blue-500 animate-ping mr-1" />
              )}
              <span>{message}</span>
            </div>
          </Alert>
        )}
      </div>
    </Card>

    {imports.length > 0 && (
      <Card title="আগের স্ক্যান" subtitle="যেকোনো স্ক্যানে ক্লিক করে তার ফলাফল ও প্রোগ্রেস দেখুন">
        <div className="flex flex-wrap gap-2">
          {imports.map((row) => {
            const isSelected = current?.id === row.id;
            const statusColor =
              row.status === "completed"
                ? "bg-green-100 text-green-800 border-green-300"
                : row.status === "processing"
                  ? "bg-blue-100 text-blue-800 border-blue-300 animate-pulse"
                  : row.status === "failed"
                    ? "bg-red-100 text-red-800 border-red-300"
                    : "bg-amber-100 text-amber-800 border-amber-300";
            const statusLabel =
              row.status === "completed"
                ? "সম্পন্ন"
                : row.status === "processing"
                  ? "চলছে"
                  : row.status === "failed"
                    ? "ব্যর্থ"
                    : "অপেক্ষায়";

            return (
              <button
                key={row.id}
                onClick={() => openImport(row.id)}
                className={`border rounded-lg px-3 py-2 text-sm flex items-center gap-2 transition-all ${
                  isSelected
                    ? "border-purple-600 bg-purple-50 shadow-xs ring-2 ring-purple-300"
                    : "border-gray-200 hover:bg-gray-50 text-gray-700"
                }`}
              >
                <span className="font-medium truncate max-w-[200px]" title={row.filename}>
                  {row.filename}
                </span>
                <span className="text-gray-400">·</span>
                <span className="text-xs text-gray-500">{row.subject}</span>
                <span className="text-gray-400">·</span>
                <span className="text-xs text-gray-600">
                  {row.processed_pages}/{row.total_pages} page
                </span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${statusColor}`}>
                  {statusLabel}
                </span>
              </button>
            );
          })}
        </div>
      </Card>
    )}

    {current && <>
      <Card title={`OCR: ${current.filename}`}>
        <p className="text-sm">{current.status === "queued" ? "অপেক্ষায় আছে" : current.status === "processing" ? "OCR চলছে" : current.status === "completed" ? "OCR সম্পন্ন" : "OCR ব্যর্থ হয়েছে"} · {current.processed_pages}/{current.total_pages} পৃষ্ঠা</p>
        {current.status === "queued" && <p className="text-xs text-gray-500 mt-2">OCR worker চালু হলে কাজ শুরু হবে। দীর্ঘ সময় অপেক্ষায় থাকলে সার্ভার পরিচালনাকারীকে জানান।</p>}
        {current.status === "failed" && <Alert>{current.error || "OCR করা যায়নি। আবার চেষ্টা করুন।"}</Alert>}
      </Card>
      <Card title="Original file">
        {current.filename.toLowerCase().endsWith(".pdf")
          ? <iframe title="Original question PDF" src={api.ocrFileUrl(current.id)} className="w-full h-96 border rounded" />
          : <img alt="Original question sheet" src={api.ocrFileUrl(current.id)} className="max-h-96 mx-auto object-contain" />}
      </Card>
      {current.status === "completed" && <>
      <Card title={`Review: ${current.filename}`} subtitle="Question bank-এ যাওয়ার আগে লেখা, option ও সূত্র ঠিক করুন">
        <div className="space-y-4">
          {candidates.map((q) => <div key={q.key} className="border rounded-xl p-4 space-y-2">
            <div className="flex items-center justify-between gap-3">
              <label className="text-sm font-semibold"><input type="checkbox" className="mr-2" checked={q.selected} onChange={(e) => update(q.key, "selected", e.target.checked)} />পৃষ্ঠা {q.page} · প্রশ্ন {q.key + 1}</label>
              <select className={inputClass} value={q.qtype} onChange={(e) => update(q.key, "qtype", e.target.value)}>
                <option value="short">Short</option><option value="broad">Broad</option><option value="mcq">MCQ</option><option value="true_false">True/False</option>
              </select>
            </div>
            <textarea className={inputClass} rows={3} value={q.text} onChange={(e) => update(q.key, "text", e.target.value)} />
            {q.qtype === "mcq" && <Field label="Options (one per line)"><textarea className={inputClass} rows={4} value={q.optionsText} onChange={(e) => update(q.key, "optionsText", e.target.value)} /></Field>}
            <div className="text-sm bg-gray-50 p-2 rounded"><RichText text={q.text} /></div>
          </div>)}
          <Button onClick={save} loading={busy}>নির্বাচিত প্রশ্ন Question Bank-এ রাখুন</Button>
        </div>
      </Card>
      <Card title="পুরো extracted text" subtitle="কোনো প্রশ্ন বাদ পড়লে এখান থেকে কপি করে Question Bank-এ যোগ করুন">
        <div className="space-y-4">{current.pages.map((page) => <div key={page.page}>
          <div className="flex justify-between text-sm font-semibold mb-1"><span>পৃষ্ঠা {page.page} · {page.method === "paddle_bangla" ? "PaddleOCR" : page.method === "tesseract" ? "Tesseract fallback" : page.method}</span><button className="text-blue-600" onClick={() => navigator.clipboard.writeText(page.text)}>Copy text</button></div>
          {page.method === "failed" && <Alert>{page.error || "এই পৃষ্ঠার লেখা পড়া যায়নি।"}</Alert>}
          <pre className="whitespace-pre-wrap text-sm bg-gray-50 border rounded p-3 max-h-80 overflow-auto">{page.text}</pre>
        </div>)}</div>
      </Card>
      </>}
    </>}
  </div>;
}
