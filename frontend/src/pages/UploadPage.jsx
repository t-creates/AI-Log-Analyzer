import { useState } from "react";
import Card from "../components/Card";
import Loader from "../components/Loader";
import Alert from "../components/Alert";
import Pill from "../components/Pill";
import { uploadLogFile } from "../lib/api";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

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

  return (
    <Card title="Upload log file (CSV/TXT)">
      <div className="space-y-3">
        <input
          type="file"
          accept=".csv,.txt"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-sm p-24 border-2 border-dashed rounded-lg cursor-pointer bg-gray-50 border-gray-300 text-gray-600 hover:bg-gray-100 focus:outline-none"
        />

        <div className="flex items-center gap-3">
          <button
            onClick={onUpload}
            disabled={!file || loading}
            className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-black disabled:opacity-60"
          >
            Upload
          </button>
          {loading ? <Loader label="Uploading..." /> : null}
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
