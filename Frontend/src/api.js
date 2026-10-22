const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const V1 = `${API_BASE}/api/v1`;

async function request(path, options = {}) {
  const res = await fetch(`${V1}${path}`, options);
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    let msg = data?.detail ?? data ?? `Request failed (${res.status})`;
    if (Array.isArray(msg)) msg = msg.map((d) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return data;
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

function query(params) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") qs.append(k, v);
  });
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export const api = {
  base: API_BASE,
  health: () => request("/health"),
  setLlmKey: (body) => request("/settings/llm", json("POST", body)),

  // Documents
  listDocuments: () => request("/documents"),
  uploadDocument: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return request("/documents/upload", { method: "POST", body: fd });
  },
  deleteDocument: (id) => request(`/documents/${id}`, { method: "DELETE" }),
  reindexDocument: (id) => request(`/documents/${id}/reindex`, { method: "POST" }),

  // Chapters
  listChapters: (docId) => request(`/documents/${docId}/chapters`),
  createChapter: (docId, body) => request(`/documents/${docId}/chapters`, json("POST", body)),
  deleteChapter: (id) => request(`/chapters/${id}`, { method: "DELETE" }),
  getChapter: (id) => request(`/chapters/${id}`),
  searchChapters: (params) => request(`/chapters/search${query(params)}`),
  generateQuestions: (id, body) => request(`/chapters/${id}/generate-questions`, json("POST", body)),

  // RAG chat: { messages, chapter_id?, document_id? } -> { reply, questions, sources }
  chat: (body) => request("/chat", json("POST", body)),

  // Question bank
  listQuestions: (params) => request(`/questions${query(params)}`),
  listTopics: () => request("/questions/topics"),
  createQuestion: (body) => request("/questions", json("POST", body)),
  createQuestions: (items) => request("/questions/bulk", json("POST", items)),
  updateQuestion: (id, body) => request(`/questions/${id}`, json("PUT", body)),
  deleteQuestion: (id) => request(`/questions/${id}`, { method: "DELETE" }),
  uploadQuestions: (file, topic) => {
    const fd = new FormData();
    fd.append("file", file);
    return request(`/questions/upload${query({ topic })}`, { method: "POST", body: fd });
  },
  templateUrl: `${V1}/questions/template.csv`,

  // Question paper -> returns { blob, filename, seed }
  buildPaper: async (body) => {
    const res = await fetch(`${V1}/questions/paper`, json("POST", body));
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Request failed (${res.status})`);
    }
    const disposition = res.headers.get("content-disposition") || "";
    const filename = disposition.match(/filename="(.+?)"/)?.[1] || "question_paper.pdf";
    return { blob: await res.blob(), filename, seed: res.headers.get("x-paper-seed") };
  },
};
