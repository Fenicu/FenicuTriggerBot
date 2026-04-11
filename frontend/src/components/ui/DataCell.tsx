import React from 'react';

interface DataCellProps {
  label: string;
  value: React.ReactNode;
  clickable?: boolean;
  onClick?: () => void;
}

const DataCell: React.FC<DataCellProps> = ({ label, value, clickable, onClick }) => (
  <div
    className={`bg-elevated rounded-[10px] px-3 py-2.5 ${clickable ? 'cursor-pointer active:bg-[#3f3f46] transition-colors' : ''}`}
    onClick={clickable ? onClick : undefined}
    onKeyDown={clickable ? (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick?.(); } } : undefined}
    role={clickable ? 'button' : undefined}
    tabIndex={clickable ? 0 : undefined}
  >
    <div className="text-[10px] text-hint uppercase tracking-wider mb-1">{label}</div>
    <div className="text-[15px] font-medium">{value}</div>
  </div>
);

export default DataCell;
