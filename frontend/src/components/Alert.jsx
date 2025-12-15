export default function Alert({ kind = "error", children }) {
  const styles =
    kind === "error"
      ? "border-red-200 bg-red-50 text-red-700"
      : "border-emerald-200 bg-emerald-50 text-emerald-800";

  return (
    <div className={`rounded-lg border p-3 text-sm ${styles}`}>
      {children}
    </div>
  );
}
