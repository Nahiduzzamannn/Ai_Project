export function Card({ title, subtitle, actions, children }) {
  return (
    <section className="bg-white rounded-2xl shadow-lg border border-gray-100 overflow-hidden">
      {title && (
        <div className="bg-linear-to-r from-blue-500 to-purple-600 px-6 py-4 flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h2 className="text-lg font-semibold text-white">{title}</h2>
            {subtitle && <p className="text-blue-50 text-sm mt-0.5">{subtitle}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="p-6">{children}</div>
    </section>
  );
}

const BUTTON_STYLES = {
  primary:
    "bg-linear-to-r from-blue-500 to-purple-600 text-white hover:from-blue-600 hover:to-purple-700 disabled:from-gray-300 disabled:to-gray-400",
  secondary: "bg-white text-gray-700 border border-gray-300 hover:bg-gray-50 disabled:text-gray-400",
  danger: "bg-white text-red-600 border border-red-200 hover:bg-red-50 disabled:text-gray-400",
};

export function Button({ variant = "primary", loading, children, className = "", ...props }) {
  return (
    <button
      {...props}
      disabled={loading || props.disabled}
      className={`inline-flex items-center justify-center gap-2 font-semibold text-sm px-4 py-2 rounded-lg transition-colors disabled:cursor-not-allowed ${BUTTON_STYLES[variant]} ${className}`}
    >
      {loading && <Spinner />}
      {children}
    </button>
  );
}

export function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}

export function Alert({ kind = "error", children, onClose }) {
  if (!children) return null;
  const styles =
    kind === "error"
      ? "bg-red-50 border-red-500 text-red-800"
      : kind === "success"
        ? "bg-green-50 border-green-500 text-green-800"
        : "bg-blue-50 border-blue-500 text-blue-800";
  return (
    <div className={`border-l-4 p-3 rounded-lg text-sm flex justify-between gap-4 ${styles}`}>
      <div className="whitespace-pre-wrap">{children}</div>
      {onClose && (
        <button onClick={onClose} className="opacity-60 hover:opacity-100" aria-label="Dismiss">
          ✕
        </button>
      )}
    </div>
  );
}

export function Field({ label, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-xs font-medium text-gray-600 mb-1">{label}</span>
      {children}
    </label>
  );
}

export function Badge({ children, color = "gray" }) {
  const colors = {
    gray: "bg-gray-100 text-gray-700",
    blue: "bg-blue-100 text-blue-700",
    purple: "bg-purple-100 text-purple-700",
    green: "bg-green-100 text-green-700",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-red-100 text-red-700",
  };
  return (
    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full ${colors[color]}`}>
      {children}
    </span>
  );
}

export function QuestionView({ q }) {
  return (
    <div>
      <p className="text-gray-900">{q.text}</p>
      {q.options && q.qtype === "mcq" && (
        <ol className="mt-1 ml-5 text-sm text-gray-700 list-[lower-alpha]">
          {q.options.map((o, i) => (
            <li key={i} className={o === q.answer ? "font-semibold text-green-700" : ""}>
              {o}
            </li>
          ))}
        </ol>
      )}
      {q.answer && q.qtype !== "mcq" && (
        <p className="mt-1 text-sm text-green-700">
          <span className="font-semibold">Answer:</span> {q.answer}
        </p>
      )}
    </div>
  );
}
