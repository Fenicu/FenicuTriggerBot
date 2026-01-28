import React from 'react';
import { Search, Filter, ArrowUpDown } from 'lucide-react';

interface TriggerFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  status: string;
  onStatusChange: (value: string) => void;
  sortBy: string;
  onSortByChange: (value: string) => void;
  sortOrder: string;
  onSortOrderChange: (value: string) => void;
  children?: React.ReactNode;
}

const TriggerFilters: React.FC<TriggerFiltersProps> = ({
  search,
  onSearchChange,
  status,
  onStatusChange,
  sortBy,
  onSortByChange,
  sortOrder,
  onSortOrderChange,
  children,
}) => {
  return (
    <div className="bg-section-bg p-4 rounded-xl mb-4 flex flex-col md:flex-row gap-4 items-center border border-black/5">
      <div className="relative flex-1 w-full">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-hint" size={18} />
        <input
          type="text"
          placeholder="Search triggers..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="w-full pl-10 pr-4 py-2 bg-bg rounded-lg border border-secondary-bg focus:border-link focus:outline-none transition-colors"
        />
      </div>

      {children}

      <div className="flex gap-2 w-full md:w-auto overflow-x-auto pb-1 md:pb-0">
        <div className="relative min-w-35">
          <Filter className="absolute left-3 top-1/2 transform -translate-y-1/2 text-hint" size={16} />
          <select
            value={status}
            onChange={(e) => onStatusChange(e.target.value)}
            className="w-full pl-9 pr-8 py-2 bg-bg rounded-lg border border-secondary-bg appearance-none focus:border-link focus:outline-none cursor-pointer"
          >
            <option value="all">All Statuses</option>
            <option value="safe">Safe</option>
            <option value="pending">Pending</option>
            <option value="flagged">Flagged</option>
            <option value="banned">Banned</option>
          </select>
          <div className="absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none text-hint text-xs">
            ▼
          </div>
        </div>

        <div className="relative min-w-35">
          <ArrowUpDown className="absolute left-3 top-1/2 transform -translate-y-1/2 text-hint" size={16} />
          <select
            value={sortBy}
            onChange={(e) => onSortByChange(e.target.value)}
            className="w-full pl-9 pr-8 py-2 bg-bg rounded-lg border border-secondary-bg appearance-none focus:border-link focus:outline-none cursor-pointer"
          >
            <option value="created_at">Date Created</option>
            <option value="key_phrase">Key Phrase</option>
          </select>
          <div className="absolute right-3 top-1/2 transform -translate-y-1/2 pointer-events-none text-hint text-xs">
            ▼
          </div>
        </div>

        <button
          onClick={() => onSortOrderChange(sortOrder === 'asc' ? 'desc' : 'asc')}
          className="px-3 py-2 bg-bg rounded-lg border border-secondary-bg hover:bg-secondary-bg transition-colors text-hint hover:text-text"
          title={sortOrder === 'asc' ? 'Ascending' : 'Descending'}
        >
          {sortOrder === 'asc' ? '↑' : '↓'}
        </button>
      </div>
    </div>
  );
};

export default TriggerFilters;
