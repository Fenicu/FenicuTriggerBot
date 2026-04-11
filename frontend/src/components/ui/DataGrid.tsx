import React from 'react';

interface DataGridProps {
  children: React.ReactNode;
  columns?: 2 | 3 | 4;
}

const colsClass: Record<number, string> = {
  2: 'grid-cols-2',
  3: 'grid-cols-3',
  4: 'grid-cols-4',
};

const DataGrid: React.FC<DataGridProps> = ({ children, columns = 2 }) => (
  <div className={`grid ${colsClass[columns]} gap-2`}>
    {children}
  </div>
);

export default DataGrid;
