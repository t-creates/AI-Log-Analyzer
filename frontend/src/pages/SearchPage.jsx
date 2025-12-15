import { useState } from "react";
import Alert from "../components/Alert";
import Card from "../components/Card";
import Pill from "../components/Pill";
import Loader from "../components/Loader";
import { postQuery } from "../lib/api";

export default function SearchPage() {
  const [question, setQuestion] = useState("Were there any pressure drops last week?");
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function run(e) {
    e?.preventDefault?.();
    setErr("");
    setLoading(true);
    setResult(null);
    try {
      const data = await postQuery(question.trim());
      setResult(data);
    } catch (ex) {
      setErr(ex.message || "Query failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card title="Ask a question">
        <form onSubmit={run} className="space-y-3">
          <textarea
            className="w-full rounded-lg border border-gray-300 bg-white p-3 text-sm outline-none focus:border-gray-900"
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
          <div className="flex items-center gap-3">
            <button
              type="submit"
              className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
              disabled={loading || !question.trim()}
            >
              Run search
            </button>
            {loading ? <Loader label="Searching..." /> : null}
          </div>
          {err ? <Alert>{err}</Alert> : null}
        </form>
      </Card>

      <Card title="Result">
        {!result && !loading ? (
          <div className="text-sm text-gray-600">Run a search to see results.</div>
        ) : null}

        {result ? (
          <div className="space-y-4">
            <div>
              <div className="mb-1 text-sm font-semibold">Answer</div>
              <div className="rounded-lg bg-gray-50 p-3 text-sm">{result.answer}</div>
            </div>

            <div>
              <div className="mb-2 text-sm font-semibold">Relevant logs</div>
              <div className="space-y-2">
                {(result.relevant_logs || []).map((l) => (
                  <div key={l.log_id} className="rounded-lg border border-gray-200 bg-white p-3">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
                      <Pill>{l.log_id}</Pill>
                      <Pill>{l.timestamp}</Pill>
                      <Pill>{l.source}</Pill>
                      <Pill>{l.severity}</Pill>
                      <Pill>score: {l.relevance_score}</Pill>
                    </div>
                    <div className="mt-2 text-sm">{l.message}</div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-1 text-sm font-semibold">Suggested follow-up</div>
              <div className="rounded-lg bg-gray-50 p-3 text-sm">{result.suggested_followup}</div>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
