import { useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL;

export default function App() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleUpload(e) {
    e.preventDefault();
    setErr("");
    setResult(null);

    if (!file) {
      setErr("Please select a PDF file first.");
      return;
    }
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setErr("Only PDF files are allowed.");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/api/v1/documents/upload`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        setErr(data?.detail || "Upload failed");
        return;
      }

      setResult(data);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-linear-to-br from-blue-50 via-indigo-50 to-purple-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-4xl mx-auto px-6 py-4">
          <h1 className="text-3xl font-bold text-transparent bg-clip-text bg-linear-to-r from-blue-600 to-purple-600">
            PDF Document Upload System
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            <span className="font-medium">API Endpoint:</span> {API_BASE}
          </p>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-4xl mx-auto px-6 py-12">
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
          {/* Card Header */}
          <div className="bg-linear-to-r from-blue-500 to-purple-600 px-8 py-6">
            <h2 className="text-2xl font-semibold text-white">
              Upload Your PDF Document
            </h2>
            <p className="text-blue-50 mt-2">
              Select a PDF file from your device and upload it to the server
            </p>
          </div>

          {/* Upload Form */}
          <div className="px-8 py-8">
            <form onSubmit={handleUpload} className="space-y-6">
              {/* File Input */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-3">
                  Select PDF File
                </label>
                <div className="relative">
                  <input
                    type="file"
                    accept="application/pdf"
                    onChange={(e) => setFile(e.target.files?.[0] || null)}
                    className="block w-full text-sm text-gray-600
                      file:mr-4 file:py-3 file:px-6
                      file:rounded-lg file:border-0
                      file:text-sm file:font-semibold
                      file:bg-linear-to-r file:from-blue-500 file:to-purple-600
                      file:text-white
                      hover:file:from-blue-600 hover:file:to-purple-700
                      file:cursor-pointer file:transition-all
                      cursor-pointer
                      border-2 border-dashed border-gray-300 rounded-lg
                      p-4 hover:border-blue-400 transition-colors"
                  />
                </div>
                {file && (
                  <p className="mt-3 text-sm text-gray-600 flex items-center">
                    <svg
                      className="w-5 h-5 mr-2 text-green-500"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    Selected:{" "}
                    <span className="font-medium ml-1">{file.name}</span>
                  </p>
                )}
              </div>

              {/* Upload Button */}
              <button
                type="submit"
                disabled={loading || !file}
                className="w-full bg-linear-to-r from-blue-500 to-purple-600 
                  text-white font-semibold py-4 px-6 rounded-lg
                  hover:from-blue-600 hover:to-purple-700
                  disabled:from-gray-300 disabled:to-gray-400 
                  disabled:cursor-not-allowed
                  transform transition-all duration-200
                  hover:scale-[1.02] active:scale-[0.98]
                  shadow-lg hover:shadow-xl
                  flex items-center justify-center"
              >
                {loading ? (
                  <>
                    <svg
                      className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      ></circle>
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      ></path>
                    </svg>
                    Uploading...
                  </>
                ) : (
                  <>
                    <svg
                      className="w-5 h-5 mr-2"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                      />
                    </svg>
                    Upload PDF
                  </>
                )}
              </button>
            </form>

            {/* Error Message */}
            {err && (
              <div className="mt-6 bg-red-50 border-l-4 border-red-500 p-4 rounded-lg">
                <div className="flex">
                  <svg
                    className="w-6 h-6 text-red-500 mr-3 shrink-0"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                    />
                  </svg>
                  <div>
                    <h3 className="text-red-800 font-semibold">Error</h3>
                    <p className="text-red-700 text-sm mt-1">{err}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Success Response */}
            {result && (
              <div className="mt-6 bg-green-50 border-l-4 border-green-500 rounded-lg overflow-hidden">
                <div className="p-4">
                  <div className="flex items-center mb-3">
                    <svg
                      className="w-6 h-6 text-green-500 mr-3"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    <h3 className="text-green-800 font-semibold text-lg">
                      Upload Successful!
                    </h3>
                  </div>
                  <div className="bg-white rounded-lg p-4 border border-green-200">
                    <h4 className="text-sm font-semibold text-gray-700 mb-2">
                      Server Response:
                    </h4>
                    <pre className="text-xs text-gray-800 overflow-x-auto bg-gray-50 p-3 rounded border border-gray-200">
                      {JSON.stringify(result, null, 2)}
                    </pre>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Info Cards section removed */}
      </main>

      {/* Footer */}
      <footer className="max-w-4xl mx-auto px-6 py-8 mt-12">
        <div className="text-center text-gray-500 text-sm">
          <p>© 2026 PDF Upload System. Powered by FastAPI & React.</p>
        </div>
      </footer>
    </div>
  );
}
