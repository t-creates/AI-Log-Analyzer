import { useState } from "react";
import Card from "../components/Card";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import Pill from "../components/Pill";
import { uploadLogFile, uploadSampleLogs } from "../lib/api";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);
  const [sampleLoading, setSampleLoading] = useState(false);

  async function onUpload() {
    setErr("");
    setRes(null);
    if (!file) return;

    setLoading(true);
    try {
      const data = await uploadLogFile(file);
      setRes(data);
    } catch (e) {
      setErr(e.message || "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  async function onUseSample() {
    setErr("");
    setRes(null);
    setSampleLoading(true);
    try {
      const data = await uploadSampleLogs();
      setRes(data);
    } catch (e) {
      setErr(e.message || "Sample upload failed");
    } finally {
      setSampleLoading(false);
    }
  }

  return (
    <Card title="Upload log file (CSV/TXT)">
      <div className="space-y-3">
        <input
          type="file"
          accept=".csv,.txt"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-sm p-24 border-2 border-dashed rounded-lg cursor-pointer bg-gray-50 border-gray-300 text-gray-600 hover:bg-gray-100 focus:outline-none"
        />

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={onUpload}
            disabled={!file || loading || sampleLoading}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
          >
            Upload
          </button>
          <button
            onClick={onUseSample}
            disabled={loading || sampleLoading}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-60"
          >
            Use sample data
          </button>
          {loading ? <Loader label="Uploading..." /> : null}
          {!loading && sampleLoading ? <Loader label="Loading sample..." /> : null}
        </div>

        {err ? <Alert>{err}</Alert> : null}

        {res ? (
          <div className="space-y-3">
            <Alert kind="success">
              Upload complete — parsed <b>{res.entries_parsed}</b> entries (file_id: <b>{res.file_id}</b>)
            </Alert>

            <div className="flex flex-wrap gap-2">
              <Pill>Status: {res.status}</Pill>
              <Pill>Earliest: {res.date_range?.earliest}</Pill>
              <Pill>Latest: {res.date_range?.latest}</Pill>
            </div>

            <div className="rounded-lg bg-gray-50 p-3">
              <div className="mb-2 text-sm font-semibold">Severity breakdown</div>
              <div className="flex flex-wrap gap-2">
                {Object.entries(res.severity_breakdown || {}).map(([k, v]) => (
                  <Pill key={k}>
                    {k}: {v}
                  </Pill>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
