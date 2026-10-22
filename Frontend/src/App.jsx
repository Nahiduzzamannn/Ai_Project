import { useEffect, useState } from "react";
import { api } from "./api";
import { Badge } from "./components/ui";
import DocumentsTab from "./components/DocumentsTab";
import ChatTab from "./components/ChatTab";
import QuestionBankTab from "./components/QuestionBankTab";
import PaperTab from "./components/PaperTab";
import AiKeyDialog from "./components/AiKeyDialog";

const TABS = [
  { id: "documents", label: "1. Documents" },
  { id: "chapters", label: "2. AI Question Chat" },
  { id: "bank", label: "3. Question Bank" },
  { id: "paper", label: "4. Question Paper" },
];

export default function App() {
  const [tab, setTab] = useState("documents");
  const [health, setHealth] = useState(null);
  const [documents, setDocuments] = useState([]);
  // Question IDs picked in the bank, used by the paper builder
  const [selectedIds, setSelectedIds] = useState([]);
  const [showKeyDialog, setShowKeyDialog] = useState(false);

  function refreshDocuments() {
    return api.listDocuments().then(setDocuments).catch(() => setDocuments([]));
  }

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: "down" }));
    api.listDocuments().then(setDocuments).catch(() => setDocuments([]));
  }, []);

  return (
    <div className="min-h-screen bg-linear-to-br from-blue-50 via-indigo-50 to-purple-50">
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-transparent bg-clip-text bg-linear-to-r from-blue-600 to-purple-600">
              AI Question Generator
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              PDF → chapter search → AI questions → question bank → shuffled question papers
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {health?.status === "ok" ? (
              <>
                <Badge color="green">API online</Badge>
                <Badge color={health.elasticsearch ? "green" : "amber"}>
                  Elasticsearch {health.elasticsearch ? "on" : "off (Postgres fallback)"}
                </Badge>
                <button onClick={() => setShowKeyDialog(true)} title="Set the AI API key">
                  <Badge color={health.ai_agent?.configured ? "green" : "red"}>
                    AI: {health.ai_agent?.configured ? health.ai_agent.model : "no API key — click to set"}
                  </Badge>
                </button>
              </>
            ) : health ? (
              <Badge color="red">API offline ({api.base})</Badge>
            ) : null}
          </div>
        </div>
        <nav className="max-w-6xl mx-auto px-4 sm:px-6 flex gap-1 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
                tab === t.id
                  ? "border-purple-600 text-purple-700"
                  : "border-transparent text-gray-500 hover:text-gray-800"
              }`}
            >
              {t.label}
              {t.id === "paper" && selectedIds.length > 0 && (
                <span className="ml-2 text-xs bg-purple-600 text-white rounded-full px-2">
                  {selectedIds.length}
                </span>
              )}
            </button>
          ))}
        </nav>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        {tab === "documents" && (
          <DocumentsTab documents={documents} onChanged={refreshDocuments} />
        )}
        {tab === "chapters" && (
          <ChatTab documents={documents} onNeedKey={() => setShowKeyDialog(true)} />
        )}
        {tab === "bank" && (
          <QuestionBankTab
            documents={documents}
            selectedIds={selectedIds}
            setSelectedIds={setSelectedIds}
            onMakePaper={() => setTab("paper")}
          />
        )}
        {tab === "paper" && (
          <PaperTab
            documents={documents}
            selectedIds={selectedIds}
            setSelectedIds={setSelectedIds}
          />
        )}
      </main>

      {showKeyDialog && (
        <AiKeyDialog
          onClose={() => setShowKeyDialog(false)}
          onSaved={() => {
            setShowKeyDialog(false);
            api.health().then(setHealth).catch(() => {});
          }}
        />
      )}

      <footer className="max-w-6xl mx-auto px-6 pb-8 text-center text-gray-500 text-sm">
        Powered by FastAPI, pgvector, Elasticsearch & React.
      </footer>
    </div>
  );
}
