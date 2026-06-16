interface SegmentControlProps<T extends string | number> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}

function SegmentControl<T extends string | number>({ options, value, onChange }: SegmentControlProps<T>) {
  return (
    <div className="flex gap-1 bg-elevated rounded-[10px] p-[3px]">
      {options.map((opt) => (
        <button
          key={String(opt.value)}
          type="button"
          onClick={() => onChange(opt.value)}
          className={`flex-1 py-[7px] rounded-lg text-[13px] font-medium text-center transition-all ${
            value === opt.value
              ? 'bg-button text-button-text shadow-[0_1px_2px_rgba(0,0,0,0.35)]'
              : 'text-hint hover:text-text'
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export default SegmentControl;
