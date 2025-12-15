export default function Pill({ children }) {
  return (
    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700">
      {children}
    </span>
  );
}
