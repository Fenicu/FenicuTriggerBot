import React from 'react';
import FilterBar from './ui/FilterBar';
import FilterChip from './ui/FilterChip';

interface TriggerFiltersProps {
  search: string;
  onSearchChange: (value: string) => void;
  status: string;
  onStatusChange: (value: string) => void;
  sortOrder: string;
  onSortOrderChange: (value: string) => void;
  children?: React.ReactNode;
}

const TriggerFilters: React.FC<TriggerFiltersProps> = ({
  search, onSearchChange, status, onStatusChange, sortOrder, onSortOrderChange, children,
}) => (
  <FilterBar
    search={search}
    onSearchChange={onSearchChange}
    searchPlaceholder="Поиск триггеров…"
    sortOrder={sortOrder as 'asc' | 'desc'}
    onSortOrderChange={(v) => onSortOrderChange(v)}
  >
    <FilterChip active={status === 'all'} onClick={() => onStatusChange('all')}>Все</FilterChip>
    <FilterChip active={status === 'safe'} onClick={() => onStatusChange('safe')}>Чисто</FilterChip>
    <FilterChip active={status === 'pending'} onClick={() => onStatusChange('pending')}>В очереди</FilterChip>
    <FilterChip active={status === 'flagged'} onClick={() => onStatusChange('flagged')}>Помечен</FilterChip>
    {children}
  </FilterBar>
);

export default TriggerFilters;
