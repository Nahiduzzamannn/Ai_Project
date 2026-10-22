import { useEffect, useState } from "react";
import { api } from "../api";
import { Alert, Button, Card, Field } from "./ui";
import { inputClass } from "./constants";

export default function PaperTab({ documents, selectedIds, setSelectedIds }) {
  const [mode, setMode] = useState(selectedIds.length > 0 ? "selected" : "random");
  const [topics, setTopics] = useState([]);
  const [form, setForm] = useState({
    title: "Class Test",
    subtitle: "",
    duration: "1 hour",
    instructions: "Answer all questions. Figures in the right margin indicate full marks.",
    num_mcq: 10,
    num_true_false: 0,
    num_short: 4,
    num_broad: 2,
    topic: "",
    difficulty: "",
    document_id: "",
    num_sets: 4,
    shuffle_questions: true,
    shuffle_options: true,
    include_answer_key: true,
    seed: "",
  });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.listTopics().then(setTopics).catch(() => {});
  }, []);

  const set = (k) => (e) => {
    const t = e.target;
    setForm({ ...form, [k]: t.type === "checkbox" ? t.checked : t.type === "number" ? Number(t.value) : t.value });
  };

  async function build(e) {
    e.preventDefault();
    setErr("");
    setMsg("");
    const body = {
      title: form.title,
      subtitle: form.subtitle || null,
      duration: form.duration || null,
      instructions: form.instructions || null,
      num_sets: form.num_sets,
      shuffle_questions: form.shuffle_questions,
      shuffle_options: form.shuffle_options,
      include_answer_key: form.include_answer_key,
      seed: form.seed === "" ? null : Number(form.seed),
    };
    if (mode === "selected") {
      if (selectedIds.length === 0) return setErr("No questions selected. Pick them in the Question Bank tab.");
      body.question_ids = selectedIds;
    } else {
      Object.assign(body, {
        num_mcq: form.num_mcq,
        num_true_false: form.num_true_false,
        num_short: form.num_short,
        num_broad: form.num_broad,
        topic: form.topic || null,
        difficulty: form.difficulty || null,
        document_id: form.document_id ? Number(form.document_id) : null,
      });
    }

    setLoading(true);
    try {
      const { blob, filename, seed } = await api.buildPaper(body);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      setMsg(
        `Downloaded ${filename} with ${form.num_sets} set(s).\n` +
          `Seed ${seed}: enter it again to rebuild exactly the same paper.`
      );
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={build} className="grid lg:grid-cols-2 gap-6">
      <Card title="1. Choose questions">
        <div className="flex gap-2 mb-4">
          {[
            ["random", "Random from bank"],
            ["selected", `Selected in bank (${selectedIds.length})`],
          ].map(([k, label]) => (
            <button
              type="button"
              key={k}
              onClick={() => setMode(k)}
              className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${mode === k ? "bg-purple-600 text-white border-purple-600" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`}
            >
              {label}
            </button>
          ))}
        </div>

        {mode === "random" ? (
          <div className="space-y-3">
            <p className="text-sm text-gray-500">
              How many questions of each type to pick at random from the bank:
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <Field label="MCQ">
                <input type="number" min="0" className={inputClass} value={form.num_mcq} onChange={set("num_mcq")} />
              </Field>
              <Field label="True/False">
                <input type="number" min="0" className={inputClass} value={form.num_true_false} onChange={set("num_true_false")} />
              </Field>
              <Field label="Short">
                <input type="number" min="0" className={inputClass} value={form.num_short} onChange={set("num_short")} />
              </Field>
              <Field label="Broad">
                <input type="number" min="0" className={inputClass} value={form.num_broad} onChange={set("num_broad")} />
              </Field>
            </div>
            <div className="grid sm:grid-cols-3 gap-3">
              <Field label="Topic / chapter">
                <select className={inputClass} value={form.topic} onChange={set("topic")}>
                  <option value="">Any topic</option>
                  {topics.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="Difficulty">
                <select className={inputClass} value={form.difficulty} onChange={set("difficulty")}>
                  <option value="">Any</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </select>
              </Field>
              <Field label="From document">
                <select className={inputClass} value={form.document_id} onChange={set("document_id")}>
                  <option value="">Any</option>
                  {documents.map((d) => <option key={d.id} value={d.id}>{d.title}</option>)}
                </select>
              </Field>
            </div>
          </div>
        ) : (
          <div className="text-sm text-gray-600 space-y-2">
            {selectedIds.length === 0 ? (
              <p>No questions selected yet. Tick questions in the Question Bank tab.</p>
            ) : (
              <>
                <p>
                  Using <b>{selectedIds.length}</b> selected question(s): IDs{" "}
                  <span className="text-gray-500">{selectedIds.join(", ")}</span>
                </p>
                <button type="button" className="text-red-600 hover:underline" onClick={() => setSelectedIds([])}>
                  Clear selection
                </button>
              </>
            )}
          </div>
        )}
      </Card>

      <Card title="2. Paper settings">
        <div className="space-y-3">
          <Field label="Title">
            <input className={inputClass} value={form.title} onChange={set("title")} required />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Subtitle (class, subject...)">
              <input className={inputClass} value={form.subtitle} onChange={set("subtitle")} />
            </Field>
            <Field label="Time">
              <input className={inputClass} value={form.duration} onChange={set("duration")} />
            </Field>
          </div>
          <Field label="Instructions">
            <input className={inputClass} value={form.instructions} onChange={set("instructions")} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Number of sets (A, B, C...)">
              <input type="number" min="1" max="26" className={inputClass} value={form.num_sets} onChange={set("num_sets")} />
            </Field>
            <Field label="Seed (optional, repeatable shuffle)">
              <input type="number" className={inputClass} placeholder="random" value={form.seed} onChange={set("seed")} />
            </Field>
          </div>
          <div className="space-y-1.5 text-sm text-gray-700">
            <label className="flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4 accent-purple-600" checked={form.shuffle_questions} onChange={set("shuffle_questions")} />
              Shuffle question order in each set
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4 accent-purple-600" checked={form.shuffle_options} onChange={set("shuffle_options")} />
              Shuffle MCQ options in each set
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" className="h-4 w-4 accent-purple-600" checked={form.include_answer_key} onChange={set("include_answer_key")} />
              Add an answer key for every set
            </label>
          </div>
          <Button type="submit" loading={loading} className="w-full">
            {loading ? "Building PDF..." : "Download question paper PDF"}
          </Button>
          <Alert onClose={() => setErr("")}>{err}</Alert>
          <Alert kind="success" onClose={() => setMsg("")}>{msg}</Alert>
          <p className="text-xs text-gray-500">
            Set A keeps the original order. Every other set has the same questions, shuffled
            within each section (MCQ, True/False, Short, Broad).
          </p>
        </div>
      </Card>
    </form>
  );
}
