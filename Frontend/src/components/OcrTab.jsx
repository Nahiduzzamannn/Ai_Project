import { useEffect, useState } from "react";
import { api } from "../api";
import { Alert, Button, Card, Field, RichText } from "./ui";
import { inputClass } from "./constants";

export default function OcrTab({ onSaved }) {
  const [file, setFile] = useState(null);
  const [subject, setSubject] = useState("বাংলা");
  const [forceOcr, setForceOcr] = useState(false);
  const [imports, setImports] = useState([]);
  const [current, setCurrent] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => { api.listOcrImports().then(setImports).catch(() => {}); }, []);

  function showImport(row) {
    setCurrent(row);
    setCandidates(row.candidates.map((q, i) => ({ ...q, key: i, selected: true, optionsText: (q.options || []).join("\n") })));
  }

  async function upload(e) {
    e.preventDefault();
    setBusy(true); setError(""); setMessage("");
    try {
      const row = await api.createOcrImport(file, subject.trim(), forceOcr);
      showImport(row);
      setImports(await api.listOcrImports());
      setMessage(`${row.pages.length} page থেকে ${row.candidates.length}টি সম্ভাব্য প্রশ্ন পাওয়া গেছে। দেখে সংশোধন করুন।`);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function openImport(id) {
    setError("");
    try { showImport(await api.getOcrImport(id)); }
    catch (err) { setError(err.message); }
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
      <label className="inline-flex items-center gap-2 text-sm mt-3"><input type="checkbox" checked={forceOcr} onChange={(e) => setForceOcr(e.target.checked)} />PDF-এর embedded text ভুল হলে সব পৃষ্ঠা OCR করুন</label>
      <p className="text-xs text-gray-500 mt-3">পরিষ্কার, সোজা ছবি ভালো ফল দেয়। গণিতের সূত্র OCR-এ ভুল হতে পারে; $...$ দিয়ে LaTeX লিখে browser preview দেখুন।</p>
      <div className="mt-3"><Alert>{error}</Alert><Alert kind="success">{message}</Alert></div>
    </Card>

    {imports.length > 0 && <Card title="আগের স্ক্যান">
      <div className="flex flex-wrap gap-2">{imports.map((row) => <button key={row.id} onClick={() => openImport(row.id)} className="border rounded-lg px-3 py-2 text-sm hover:bg-blue-50">{row.filename} · {row.subject} · {row.page_count} page</button>)}</div>
    </Card>}

    {current && <>
      <Card title="Original file">
        {current.filename.toLowerCase().endsWith(".pdf")
          ? <iframe title="Original question PDF" src={api.ocrFileUrl(current.id)} className="w-full h-96 border rounded" />
          : <img alt="Original question sheet" src={api.ocrFileUrl(current.id)} className="max-h-96 mx-auto object-contain" />}
      </Card>
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
          <div className="flex justify-between text-sm font-semibold mb-1"><span>পৃষ্ঠা {page.page} · {page.method === "ocr" ? "OCR" : "PDF text"}</span><button className="text-blue-600" onClick={() => navigator.clipboard.writeText(page.text)}>Copy text</button></div>
          <pre className="whitespace-pre-wrap text-sm bg-gray-50 border rounded p-3 max-h-80 overflow-auto">{page.text}</pre>
        </div>)}</div>
      </Card>
    </>}
  </div>;
}
