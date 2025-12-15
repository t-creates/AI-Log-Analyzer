export default function Card({ title, children, right }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      {(title || right) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title ? <h2 className="text-lg font-semibold">{title}</h2> : <div />}
          {right ? <div>{right}</div> : null}
        </div>
      )}
      {children}
    </div>
  );
}
