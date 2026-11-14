import { useEffect, useState, useRef } from "react";
import { api } from "../api";
import { Alert, Button, Card, Field, RichText, Toast } from "./ui";
import { inputClass } from "./constants";

function SubjectCombobox({ value, onChange, topics = [] }) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filtered = topics.filter((t) =>
    t.toLowerCase().includes((value || "").toLowerCase())
  );

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          type="text"
          className={`${inputClass} pr-8`}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            if (topics.length > 0) setOpen(true);
          }}
          placeholder="যেমন: বাংলা"
          required
        />
        {topics.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((prev) => !prev)}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-xs p-1.5 focus:outline-none"
            title="পূর্ববর্তী বিষয়ের তালিকা"
          >
            ▼
          </button>
        )}
      </div>

      {open && topics.length > 0 && (
        <div className="absolute left-0 right-0 top-full mt-1.5 z-50 max-h-48 overflow-y-auto bg-white border border-gray-300 rounded-lg shadow-xl py-1">
          {filtered.length > 0 ? (
            filtered.map((t) => (
              <button
                key={t}
                type="button"
                className={`w-full text-left px-3 py-2 text-sm hover:bg-blue-50 transition-colors ${
                  value === t ? "bg-blue-50 font-semibold text-blue-700" : "text-gray-700"
                }`}
                onClick={() => {
                  onChange(t);
                  setOpen(false);
                }}
              >
                {t}
              </button>
            ))
          ) : (
            <div className="px-3 py-2 text-xs text-gray-400 italic">
              নতুন বিষয় হিসেবে যোগ হবে: "{value}"
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function OcrTab({ onSaved }) {
  const [file, setFile] = useState(null);
  const [subject, setSubject] = useState("বাংলা");
  const [availableTopics, setAvailableTopics] = useState([]);
  const [imports, setImports] = useState([]);
  const [current, setCurrent] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [cardErrors, setCardErrors] = useState({});
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const activeImportId = current?.id;
  const activeImportStatus = current?.status;

  useEffect(() => {
    // 1. Load imports (do NOT auto-select finished jobs so initial view is clean)
    api.listOcrImports().then((items) => {
      setImports(items);
      const activeJob = items.find((it) => ["queued", "processing"].includes(it.status));
      if (activeJob) {
        api.getOcrImport(activeJob.id).then((row) => {
          showImport(row);
          setMessage(`OCR চলছে (${row.processed_pages}/${row.total_pages} পৃষ্ঠা)...`);
        }).catch(() => {});
      }
    }).catch(() => {});

    // 2. Load previously used topics only from teacher's database
    api.listTopics().then((res) => {
      if (Array.isArray(res)) {
        const cleanTopics = res.filter(Boolean);
        setAvailableTopics(cleanTopics);
        if (cleanTopics.length > 0) {
          setSubject(cleanTopics[0]);
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
          setToast({ message: "OCR সফলভাবে সম্পন্ন হয়েছে! নিচে প্রশ্নগুলো দেখুন।", kind: "success" });
        } else if (row.status === "processing") {
          setCurrent(row);
          setMessage(`OCR চলছে (${row.processed_pages}/${row.total_pages} পৃষ্ঠা)... অনুগ্রহ করে অপেক্ষা করুন।`);
        } else if (row.status === "failed") {
          setCurrent(row);
          setMessage("");
          setError(row.error || "OCR ব্যর্থ হয়েছে।");
          setToast({ message: row.error || "OCR ব্যর্থ হয়েছে।", kind: "error" });
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
      if (active) timer = setTimeout(poll, 5000);
    }
    timer = setTimeout(poll, 5000);
    return () => { active = false; clearTimeout(timer); controller?.abort(); };
  }, [activeImportId, activeImportStatus]);

  function showImport(row) {
    setCurrent(row);
    setCardErrors({});
    setCandidates((row.candidates || []).map((q, i) => ({
      ...q,
      key: i,
      selected: true,
      optionsText: (q.options || []).join("\n"),
      answer: q.answer || null,
    })));
    setImports((prev) =>
      prev.map((item) =>
        item.id === row.id
          ? { ...item, status: row.status, processed_pages: row.processed_pages, total_pages: row.total_pages }
          : item
      )
    );
  }

  function handleFileSelect(selectedFile) {
    setFile(selectedFile);
    // Instantly reset selection & messages so screen is clean for the new upload
    setCurrent(null);
    setCandidates([]);
    setCardErrors({});
    setError("");
    setMessage("");
  }

  function handleToggleImport(id) {
    if (current?.id === id) {
      // Toggle off / deselect
      setCurrent(null);
      setCandidates([]);
      setCardErrors({});
      setError("");
      setMessage("");
    } else {
      openImport(id);
    }
  }

  async function upload(e) {
    e.preventDefault();
    setBusy(true); setError(""); setMessage(""); setCardErrors({});
    try {
      const row = await api.createOcrImport(file, subject.trim());
      showImport(row);
      setMessage("ফাইল গ্রহণ করা হয়েছে। OCR শুরু হওয়ার অপেক্ষায় আছে...");
      const updatedList = await api.listOcrImports();
      setImports(updatedList);
    } catch (err) {
      setError(err.message);
      setToast({ message: err.message, kind: "error" });
    } finally {
      setBusy(false);
    }
  }

  async function openImport(id) {
    setError("");
    setMessage("");
    setCardErrors({});
    try {
      const row = await api.getOcrImport(id);
      showImport(row);
      if (row.status === "completed") {
        setMessage("OCR সম্পন্ন হয়েছে। নিচে প্রশ্নগুলো দেখে নিন।");
      } else if (["queued", "processing"].includes(row.status)) {
        setMessage(`OCR চলছে (${row.processed_pages}/${row.total_pages} পৃষ্ঠা)...`);
      }
    } catch (err) {
      setError(err.message);
      setToast({ message: err.message, kind: "error" });
    }
  }

  function update(key, field, value) {
    setCandidates((items) =>
      items.map((q) => {
        if (q.key !== key) return q;
        const updated = { ...q, [field]: value };
        // Clear error if now valid
        if (cardErrors[key]) {
          if (field === "qtype" && value !== "mcq") {
            setCardErrors((prev) => { const n = { ...prev }; delete n[key]; return n; });
          } else if (field === "optionsText") {
            const count = value.split("\n").map((o) => o.trim()).filter(Boolean).length;
            if (count >= 2) {
              setCardErrors((prev) => { const n = { ...prev }; delete n[key]; return n; });
            }
          }
        }
        return updated;
      })
    );
  }

  function addCandidate() {
    setCandidates((items) => [
      ...items,
      {
        key: Date.now(),
        page: current?.total_pages || 1,
        text: "",
        qtype: "short",
        optionsText: "",
        selected: true,
        answer: null,
      },
    ]);
  }

  function removeCandidate(key) {
    setCandidates((items) => items.filter((q) => q.key !== key));
    setCardErrors((prev) => { const n = { ...prev }; delete n[key]; return n; });
  }

  async function save() {
    const selected = candidates.filter((q) => q.selected && q.text.trim());
    if (!selected.length) {
      const msg = "Save করার জন্য অন্তত একটি প্রশ্ন বেছে নিন।";
      setError(msg);
      setToast({ message: msg, kind: "warning" });
      return;
    }

    // Client-side pre-validation: check every MCQ for at least 2 options
    const newErrors = {};
    let firstErrorCandidate = null;
    let firstErrorIndex = -1;

    for (let i = 0; i < selected.length; i++) {
      const q = selected[i];
      if (q.qtype === "mcq") {
        const validOptions = (q.optionsText || "").split("\n").map((o) => o.trim()).filter(Boolean);
        if (validOptions.length < 2) {
          newErrors[q.key] = "MCQ প্রশ্নের জন্য অন্তত ২টি অপশন থাকা আবশ্যক (প্রতি লাইনে একটি লিখুন)।";
          if (!firstErrorCandidate) {
            firstErrorCandidate = q;
            firstErrorIndex = candidates.findIndex((c) => c.key === q.key);
          }
        }
      }
    }

    if (firstErrorCandidate) {
      setCardErrors(newErrors);
      const friendlyNum = firstErrorIndex >= 0 ? firstErrorIndex + 1 : "চিহ্নিত";
      const errorMsg = `প্রশ্ন ${friendlyNum}-এ সমস্যা: MCQ প্রশ্নের জন্য অন্তত ২টি অপশন দিন অথবা ধরন 'Short' এ রূপান্তর করুন।`;
      setError(errorMsg);
      setToast({ message: errorMsg, kind: "error" });
      const el = document.getElementById(`ocr-candidate-${firstErrorCandidate.key}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
      return;
    }

    setCardErrors({});
    const questions = selected.map((q) => ({
      text: q.text.trim(),
      qtype: q.qtype,
      options: q.qtype === "mcq" ? q.optionsText.split("\n").map((o) => o.trim()).filter(Boolean) : null,
      answer: q.answer ? q.answer.trim() : null,
      marks: q.marks || (q.qtype === "mcq" ? 1 : 2),
      difficulty: q.difficulty || "medium",
      topic: current?.subject || subject,
    }));

    setBusy(true); setError("");
    try {
      await api.acceptOcrQuestions(current.id, questions);
      setToast({ message: `${questions.length}টি প্রশ্ন সফলভাবে Question Bank-এ সংরক্ষিত হয়েছে!`, kind: "success" });
      onSaved();
    } catch (err) {
      // Humanize backend 422 errors like 'questions.8: Value error...'
      const match = err.message.match(/questions\.(\d+):/);
      if (match) {
        const qIdx = parseInt(match[1], 10);
        const badQ = selected[qIdx];
        const actualNum = candidates.findIndex((c) => c.key === badQ?.key) + 1 || qIdx + 1;
        const friendlyMsg = `প্রশ্ন ${actualNum}-এ ত্রুটি: MCQ প্রশ্নের জন্য অন্তত ২টি অপশন থাকা বাধ্যতামূলক।`;
        if (badQ) {
          setCardErrors((prev) => ({ ...prev, [badQ.key]: "MCQ প্রশ্নের জন্য অন্তত ২টি অপশন দিন।" }));
          document.getElementById(`ocr-candidate-${badQ.key}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
        }
        setError(friendlyMsg);
        setToast({ message: friendlyMsg, kind: "error" });
      } else {
        setError(err.message);
        setToast({ message: err.message, kind: "error" });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      {toast && (
        <Toast
          message={toast.message}
          kind={toast.kind}
          duration={5000}
          onClose={() => setToast(null)}
        />
      )}

      <Card title="ছবি বা PDF থেকে প্রশ্ন" subtitle="বাংলা ও ইংরেজি OCR; সংরক্ষণের আগে সব প্রশ্ন দেখে নিন">
        <form onSubmit={upload} className="grid md:grid-cols-[1fr_13.5rem_auto] gap-3 items-end">
          <Field label="Question image / PDF (20 MB, PDF সর্বোচ্চ 30 পৃষ্ঠা)">
            <div className="border border-dashed border-gray-300 rounded-lg p-2 bg-gray-50/60 hover:bg-gray-50 hover:border-blue-400 transition-colors">
              <input
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff"
                onChange={(e) => handleFileSelect(e.target.files?.[0] || null)}
                required
                className="block w-full text-sm text-gray-500
                  file:mr-3 file:py-1.5 file:px-3 file:rounded-md file:border-0
                  file:text-xs file:font-semibold file:bg-blue-600 file:text-white
                  hover:file:bg-blue-700 file:cursor-pointer cursor-pointer focus:outline-none"
              />
              {!file ? (
                <span className="block text-xs text-gray-400 mt-1 pl-1">
                  কোনো ফাইল নির্বাচন করা হয়নি (PDF বা ছবি নির্বাচন করুন)
                </span>
              ) : (
                <span className="block text-xs text-blue-700 font-medium mt-1 pl-1 truncate">
                  নির্বাচিত ফাইল: {file.name} ({(file.size / (1024 * 1024)).toFixed(2)} MB)
                </span>
              )}
            </div>
          </Field>
          <Field label="বিষয়">
            <SubjectCombobox
              value={subject}
              onChange={setSubject}
              topics={availableTopics}
            />
          </Field>
          <Button type="submit" disabled={!file || !subject.trim()} loading={busy} className="h-[42px]">
            OCR করুন
          </Button>
        </form>
        <p className="text-xs text-gray-500 mt-3">
          পরিষ্কার, সোজা ছবি ভালো ফল দেয়। গণিতের সূত্র OCR-এ ভুল হতে পারে; $...$ দিয়ে LaTeX লিখে browser preview দেখুন।
        </p>
        <div className="mt-3 space-y-2">
          <Alert kind="error">{error}</Alert>
          {message && current && (
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
        <Card title="আগের স্ক্যান" subtitle="যেকোনো স্ক্যানে ক্লিক করে ফলাফল দেখুন; আবার ক্লিক করলে বন্ধ হবে">
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
                  onClick={() => handleToggleImport(row.id)}
                  title={isSelected ? "ক্লিক করে নির্বাচন বন্ধ করুন" : "ফলাফল দেখতে ক্লিক করুন"}
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

      {current && (
        <>
          <Card
            title={`OCR: ${current.filename}`}
            actions={
              <button
                type="button"
                onClick={() => {
                  setCurrent(null);
                  setCandidates([]);
                  setCardErrors({});
                  setMessage("");
                  setError("");
                }}
                className="text-white/80 hover:text-white text-xs bg-white/20 hover:bg-white/30 px-2.5 py-1 rounded transition-colors"
              >
                ✕ বন্ধ করুন
              </button>
            }
          >
            <p className="text-sm">
              {current.status === "queued"
                ? "অপেক্ষায় আছে"
                : current.status === "processing"
                  ? "OCR চলছে"
                  : current.status === "completed"
                    ? "OCR সম্পন্ন"
                    : "OCR ব্যর্থ হয়েছে"} · {current.processed_pages}/{current.total_pages} পৃষ্ঠা
            </p>
            {current.status === "queued" && (
              <p className="text-xs text-gray-500 mt-2">
                OCR worker চালু হলে কাজ শুরু হবে। দীর্ঘ সময় অপেক্ষায় থাকলে সার্ভার পরিচালনাকারীকে জানান।
              </p>
            )}
            {current.status === "failed" && <Alert>{current.error || "OCR করা যায়নি। আবার চেষ্টা করুন।"}</Alert>}
          </Card>

          <Card title="Original file">
            {current.filename.toLowerCase().endsWith(".pdf") ? (
              <iframe title="Original question PDF" src={api.ocrFileUrl(current.id)} className="w-full h-96 border rounded" />
            ) : (
              <img alt="Original question sheet" src={api.ocrFileUrl(current.id)} className="max-h-96 mx-auto object-contain" />
            )}
          </Card>

          {current.status === "completed" && (
            <>
              <Card title={`Review: ${current.filename}`} subtitle="Question bank-এ যাওয়ার আগে লেখা, option ও সূত্র ঠিক করুন">
                <div className="space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-gray-500">{candidates.length} টি সম্ভাব্য প্রশ্ন পাওয়া গেছে</span>
                    <Button variant="secondary" onClick={addCandidate}>+ প্রশ্ন যোগ করুন</Button>
                  </div>

                  {candidates.map((q) => {
                    const hasError = !!cardErrors[q.key];
                    return (
                      <div
                        key={q.key}
                        id={`ocr-candidate-${q.key}`}
                        className={`border rounded-xl p-4 space-y-2 relative bg-white transition-all ${
                          hasError
                            ? "border-red-500 ring-2 ring-red-200 bg-red-50/10 shadow-sm"
                            : "border-gray-200"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3 flex-wrap">
                          <label className="text-sm font-semibold flex items-center">
                            <input
                              type="checkbox"
                              className="mr-2 h-4 w-4 accent-purple-600"
                              checked={q.selected}
                              onChange={(e) => update(q.key, "selected", e.target.checked)}
                            />
                            পৃষ্ঠা {q.page} · প্রশ্ন {q.key + 1}
                          </label>
                          <div className="flex items-center gap-2">
                            <select
                              className={inputClass}
                              value={q.qtype}
                              onChange={(e) => update(q.key, "qtype", e.target.value)}
                            >
                              <option value="short">Short</option>
                              <option value="broad">Broad</option>
                              <option value="mcq">MCQ</option>
                              <option value="true_false">True/False</option>
                            </select>
                            <button
                              type="button"
                              onClick={() => removeCandidate(q.key)}
                              className="text-red-500 hover:text-red-700 text-xs px-2 py-1 rounded border border-red-200 hover:bg-red-50"
                              title="Remove this question"
                            >
                              Delete
                            </button>
                          </div>
                        </div>

                        {hasError && (
                          <div className="bg-red-50 border border-red-300 text-red-800 text-xs px-3 py-2 rounded-lg flex items-center justify-between gap-2">
                            <span>⚠️ {cardErrors[q.key]}</span>
                            <button
                              type="button"
                              onClick={() => update(q.key, "qtype", "short")}
                              className="bg-white border border-red-300 hover:bg-red-50 px-2 py-1 rounded font-semibold text-red-700 text-xs shrink-0"
                            >
                              Short প্রশ্নে রূপান্তর করুন
                            </button>
                          </div>
                        )}

                        <textarea
                          className={inputClass}
                          rows={3}
                          value={q.text}
                          onChange={(e) => update(q.key, "text", e.target.value)}
                        />

                        {q.qtype === "mcq" && (
                          <div className="space-y-2">
                            <Field label="Options (one per line)">
                              <textarea
                                className={`${inputClass} ${hasError ? "border-red-400 ring-1 ring-red-300" : ""}`}
                                rows={4}
                                value={q.optionsText}
                                onChange={(e) => update(q.key, "optionsText", e.target.value)}
                                placeholder="ক) অপশন ১&#10;খ) অপশন ২&#10;গ) অপশন ৩&#10;ঘ) অপশন ৪"
                              />
                            </Field>
                            {q.optionsText.split("\n").map((o) => o.trim()).filter(Boolean).length > 0 && (
                              <div className="space-y-1">
                                <span className="text-xs font-semibold text-gray-600">সঠিক উত্তর নির্বাচন করুন (ঐচ্ছিক):</span>
                                <div className="grid sm:grid-cols-2 gap-2">
                                  {q.optionsText.split("\n").map((o) => o.trim()).filter(Boolean).map((opt, optIdx) => (
                                    <label
                                      key={optIdx}
                                      className={`flex items-start gap-2 text-sm rounded-lg border p-2.5 cursor-pointer transition-colors ${
                                        q.answer === opt
                                          ? "bg-blue-50 border-blue-400 text-blue-950 ring-1 ring-blue-300"
                                          : "bg-gray-50 border-gray-200 hover:bg-gray-100 text-gray-800"
                                      }`}
                                    >
                                      <input
                                        type="radio"
                                        name={`answer-${q.key}`}
                                        checked={q.answer === opt}
                                        onChange={() => update(q.key, "answer", opt)}
                                        className="mt-0.5 accent-blue-600"
                                      />
                                      <span className="flex-1 break-words">
                                        <RichText text={opt} />
                                      </span>
                                    </label>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        <div className="text-sm bg-gray-50 p-3 rounded-lg border border-gray-200 space-y-1.5">
                          <div className="font-medium text-gray-900"><RichText text={q.text} /></div>
                          {q.qtype === "mcq" && q.optionsText && (
                            <ol className="ml-5 text-sm text-gray-700 list-[lower-alpha] space-y-1">
                              {q.optionsText.split("\n").map((o) => o.trim()).filter(Boolean).map((opt, optIdx) => (
                                <li key={optIdx} className={q.answer === opt ? "font-semibold text-green-700" : ""}>
                                  <RichText text={opt} />
                                  {q.answer === opt && <span className="ml-2 text-xs text-green-600 font-normal">✓ (সঠিক উত্তর)</span>}
                                </li>
                              ))}
                            </ol>
                          )}
                        </div>
                      </div>
                    );
                  })}

                  <div className="flex gap-3">
                    <Button onClick={save} loading={busy}>নির্বাচিত প্রশ্ন Question Bank-এ রাখুন</Button>
                    <Button variant="secondary" onClick={addCandidate}>+ প্রশ্ন যোগ করুন</Button>
                  </div>
                </div>
              </Card>

              <Card title="পুরো extracted text" subtitle="কোনো প্রশ্ন বাদ পড়লে এখান থেকে কপি করে Question Bank-এ যোগ করুন">
                <div className="space-y-4">
                  {current.pages.map((page) => (
                    <div key={page.page}>
                      <div className="flex justify-between text-sm font-semibold mb-1">
                        <span>
                          পৃষ্ঠা {page.page} · {page.method === "gemini_vision" ? "Gemini Vision" : page.method === "tesseract" ? "Tesseract fallback" : page.method}
                        </span>
                        <button className="text-blue-600 text-xs hover:underline" onClick={() => navigator.clipboard.writeText(page.text)}>
                          Copy text
                        </button>
                      </div>
                      {page.method === "failed" && <Alert>{page.error || "এই পৃষ্ঠার লেখা পড়া যায়নি।"}</Alert>}
                      <pre className="whitespace-pre-wrap text-sm bg-gray-50 border rounded p-3 max-h-80 overflow-auto">{page.text}</pre>
                    </div>
                  ))}
                </div>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
