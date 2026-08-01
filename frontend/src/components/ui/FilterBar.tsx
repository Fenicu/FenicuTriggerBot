import React from 'react';
import { Search, ArrowUpDown } from 'lucide-react';

interface FilterBarProps {
  search: string;
  onSearchChange: (v: string) => void;
  searchPlaceholder?: string;
  children?: React.ReactNode;
  sortOrder?: 'asc' | 'desc';
  onSortOrderChange?: (v: 'asc' | 'desc') => void;
}

const FilterBar: React.FC<FilterBarProps> = ({
  search, onSearchChange, searchPlaceholder = 'Поиск…', children, sortOrder, onSortOrderChange,
}) => (
  <div className="bg-surface border border-border rounded-[14px] p-3 mb-4">
    <div className="flex gap-2 mb-2.5">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-hint" size={16} />
        <input
          type="text"
          placeholder={searchPlaceholder}
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-elevated text-text border border-border rounded-[10px] text-sm outline-none focus:border-button transition-colors placeholder:text-hint"
        />
      </div>
      {onSortOrderChange && (
        <button
          type="button"
          onClick={() => onSortOrderChange(sortOrder === 'asc' ? 'desc' : 'asc')}
          className="px-3 py-2 bg-elevated border border-border rounded-[10px] text-hint hover:text-text transition-colors"
          title={sortOrder === 'asc' ? 'По возрастанию' : 'По убыванию'}
        >
          <ArrowUpDown size={16} className={sortOrder === 'asc' ? 'rotate-180' : ''} />
        </button>
      )}
    </div>
    <div className="flex gap-1.5 flex-wrap">
      {children}
    </div>
  </div>
);

export default FilterBar;
