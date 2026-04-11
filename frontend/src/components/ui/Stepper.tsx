import React from 'react';

interface StepperProps {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
}

const Stepper: React.FC<StepperProps> = ({ value, onChange, min = 1, max = 10 }) => (
  <div className="flex items-center bg-elevated rounded-[10px] overflow-hidden">
    <button
      type="button"
      onClick={() => onChange(Math.max(min, value - 1))}
      className="w-[40px] h-[34px] flex items-center justify-center text-button text-lg active:bg-button/10"
    >
      −
    </button>
    <span className="w-[36px] text-center text-[15px] font-semibold border-x border-border">
      {value}
    </span>
    <button
      type="button"
      onClick={() => onChange(Math.min(max, value + 1))}
      className="w-[40px] h-[34px] flex items-center justify-center text-button text-lg active:bg-button/10"
    >
      +
    </button>
  </div>
);

export default Stepper;
