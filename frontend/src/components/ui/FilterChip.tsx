import React from 'react';

interface FilterChipProps {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}

const FilterChip: React.FC<FilterChipProps> = ({ active, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`px-3.5 py-1.5 rounded-full text-xs font-medium transition-all ${
      active
        ? 'bg-button text-button-text border border-button'
        : 'bg-elevated text-hint border border-[#3f3f46] hover:text-text'
    }`}
  >
    {children}
  </button>
);

export default FilterChip;
