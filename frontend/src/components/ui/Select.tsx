interface SelectProps<T extends string | number> {
  label?: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}

function Select<T extends string | number>({ label, value, options, onChange }: SelectProps<T>) {
  return (
    <div className={label ? 'flex items-center justify-between py-2 gap-2' : ''}>
      {label && <span className="text-[14px] font-medium">{label}</span>}
      <div className="relative">
        <select
          value={String(value)}
          onChange={(e) => {
            const raw = e.target.value;
            const parsed = typeof value === 'number' ? (Number(raw) as T) : (raw as T);
            onChange(parsed);
          }}
          className="appearance-none bg-elevated text-text border border-border rounded-[10px] px-3.5 py-2 pr-8 text-sm cursor-pointer outline-none focus:border-button transition-colors"
        >
          {options.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>{opt.label}</option>
          ))}
        </select>
        <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-hint text-[10px] pointer-events-none">▼</span>
      </div>
    </div>
  );
}

export default Select;
