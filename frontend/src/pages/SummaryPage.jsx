import { useEffect, useState } from "react";
import Card from "../components/Card";
import Pill from "../components/Pill";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import { getSummary } from "../lib/api";

export default function SummaryPage() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setErr("");
    setLoading(true);
    try {
      const d = await getSummary();
      setData(d);
    } catch (e) {
      setErr(e.message || "Failed to load summary");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <Card
      title="AI Summary"
      right={
        <button
          onClick={refresh}
          className="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
          disabled={loading}
        >
          Refresh
        </button>
      }
    >
      {loading ? <Loader label="Generating summary..." /> : null}
      {err ? <Alert>{err}</Alert> : null}

      {data ? (
        <div className="mt-3 space-y-4">
          <div className="flex flex-wrap gap-2">
            <Pill>Generated: {data.summary_generated_at}</Pill>
            <Pill>Period: {data.period}</Pill>
            <Pill>Total entries: {data.total_entries}</Pill>
          </div>

          <div className="rounded-lg bg-gray-50 p-3">
            <div className="mb-2 text-sm font-semibold">Top incidents</div>
            <div className="space-y-2">
              {(data.top_incidents || []).map((i, idx) => (
                <div key={idx} className="rounded-lg border border-gray-200 bg-white p-3">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
                    <Pill>{i.severity}</Pill>
                    <Pill>{i.timestamp}</Pill>
                    <Pill>related: {i.related_entries}</Pill>
                  </div>
                  <div className="mt-2 text-sm font-semibold">{i.incident}</div>
                  <div className="mt-1 text-sm text-gray-700">{i.suspected_root_cause}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg bg-gray-50 p-3">
              <div className="mb-2 text-sm font-semibold">Patterns detected</div>
              <ul className="list-disc space-y-1 pl-5 text-sm text-gray-700">
                {(data.patterns_detected || []).map((p, idx) => (
                  <li key={idx}>{p}</li>
                ))}
              </ul>
            </div>

            <div className="rounded-lg bg-gray-50 p-3">
              <div className="mb-2 text-sm font-semibold">Recommended actions</div>
              <ul className="list-disc space-y-1 pl-5 text-sm text-gray-700">
                {(data.recommended_actions || []).map((a, idx) => (
                  <li key={idx}>{a}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}
