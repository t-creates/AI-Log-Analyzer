import { useState } from "react";
import UploadPage from "./pages/UploadPage";
import LogsPage from "./pages/LogsPage";
import SummaryPage from "./pages/SummaryPage";
import SearchPage from "./pages/SearchPage";

const TABS = [
  { key: "search", label: "Search" },
  { key: "summary", label: "Summary" },
  { key: "logs", label: "Logs" },
  { key: "upload", label: "Upload" },
];

export default function App() {
  const [tab, setTab] = useState("search");

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b border-gray-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
          <div>
            <h1 className="text-xl font-bold">AI Log Analyzer</h1>
            <p className="text-sm text-gray-600">Upload • Logs • Summary • FAISS Search</p>
          </div>

          <div className="flex flex-wrap gap-2">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-lg px-3 py-2 text-sm font-medium ${tab === t.key
                    ? "bg-gray-900 text-white"
                    : "bg-gray-100 text-gray-800 hover:bg-gray-200"
                  }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-4 px-4 py-6">
        {tab === "search" ? <SearchPage /> : null}
        {tab === "summary" ? <SummaryPage /> : null}
        {tab === "logs" ? <LogsPage /> : null}
        {tab === "upload" ? <UploadPage /> : null}
      </main>
    </div>
  );
}
