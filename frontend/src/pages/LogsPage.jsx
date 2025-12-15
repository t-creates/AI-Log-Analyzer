import { useEffect, useState } from "react";
import Card from "../components/Card";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import Pill from "../components/Pill";
import { getLogs } from "../lib/api";

export default function LogsPage() {
  const [source, setSource] = useState("");
  const [severity, setSeverity] = useState("");
  const [limit, setLimit] = useState(20);

  const [data, setData] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  async function fetchLogs() {
    setErr("");
    setLoading(true);
    try {
      const res = await getLogs({ source, severity, limit });
      setData(res);
    } catch (e) {
      setErr(e.message || "Failed to load logs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchLogs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <Card
        title="Browse Logs"
        right={
          <button
            onClick={fetchLogs}
            disabled={loading}
            className="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
          >
            Refresh
          </button>
        }
      >
        <div className="grid gap-3 md:grid-cols-3">
          <input
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-gray-900"
            placeholder="Source (e.g. UNIT-007)"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />
          <input
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-gray-900"
            placeholder="Severity (e.g. CRITICAL)"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          />
          <input
            type="number"
            min="1"
            max="200"
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm outline-none focus:border-gray-900"
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
          />
        </div>

        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={fetchLogs}
            disabled={loading}
            className="rounded-lg bg-gray-100 px-3 py-2 text-sm font-medium text-gray-800 hover:bg-gray-200 disabled:opacity-60"
          >
            Apply filters
          </button>
          {loading ? <Loader label="Loading logs..." /> : null}
        </div>

        {data ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <Pill>Total matched: {data.total}</Pill>
            {Object.entries(data.filters_applied || {}).map(([k, v]) => (
              <Pill key={k}>
                {k}: {v}
              </Pill>
            ))}
          </div>
        ) : null}

        {err ? <div className="mt-3"><Alert>{err}</Alert></div> : null}
      </Card>

      <Card title="Results">
        {data?.logs?.length ? (
          <div className="space-y-2">
            {data.logs.map((l) => (
              <div key={l.log_id} className="rounded-lg border border-gray-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-600">
                  <Pill>{l.log_id}</Pill>
                  <Pill>{l.timestamp}</Pill>
                  <Pill>{l.source}</Pill>
                  <Pill>{l.severity}</Pill>
                </div>
                <div className="mt-2 text-sm">{l.message}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-gray-600">{loading ? "Loading..." : "No logs returned."}</div>
        )}
      </Card>
    </div>
  );
}
