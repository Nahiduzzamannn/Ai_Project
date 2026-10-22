import { useState } from "react";
import { api } from "../api";
import { Alert, Button } from "./ui";
import { inputClass } from "./constants";

const PROVIDERS = {
  groq: { label: "Groq (recommended)", url: "https://console.groq.com/keys", hint: "starts with gsk_" },
  gemini: { label: "Google Gemini", url: "https://aistudio.google.com/apikey", hint: "starts with AIza" },
};

export default function AiKeyDialog({ onClose, onSaved }) {
  const [provider, setProvider] = useState("groq");
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const p = PROVIDERS[provider];

  async function save(e) {
    e.preventDefault();
    setErr("");
    setSaving(true);
    try {
      await api.setLlmKey({ api_key: key.trim(), provider });
      onSaved();
    } catch (e) {
      setErr(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" onClick={onClose}>
      <form
        onSubmit={save}
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden"
      >
        <div className="bg-linear-to-r from-blue-500 to-purple-600 px-6 py-4">
          <h2 className="text-lg font-semibold text-white">Connect the AI (free)</h2>
          <p className="text-blue-50 text-sm">The key is checked, then saved to Backend/backend/.env</p>
        </div>
        <div className="p-6 space-y-4">
          <div className="flex gap-2">
            {Object.entries(PROVIDERS).map(([id, v]) => (
              <button
                type="button"
                key={id}
                onClick={() => setProvider(id)}
                className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium border ${provider === id ? "bg-purple-600 text-white border-purple-600" : "border-gray-300 text-gray-700 hover:bg-gray-50"}`}
              >
                {v.label}
              </button>
            ))}
          </div>
          <ol className="text-sm text-gray-700 list-decimal pl-5 space-y-1">
            <li>
              Open{" "}
              <a href={p.url} target="_blank" rel="noreferrer" className="text-blue-600 underline">
                {p.url}
              </a>{" "}
              and sign in (free, no credit card).
            </li>
            <li>Click <b>Create API Key</b> and copy it ({p.hint}).</li>
            <li>Paste it below and click Save.</li>
          </ol>
          <input
            type="password"
            autoFocus
            className={inputClass}
            placeholder="Paste your API key here"
            value={key}
            onChange={(e) => setKey(e.target.value)}
          />
          <Alert onClose={() => setErr("")}>{err}</Alert>
          <div className="flex gap-2 justify-end">
            <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
            <Button type="submit" loading={saving} disabled={key.trim().length < 10}>
              {saving ? "Checking key..." : "Save"}
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
}
