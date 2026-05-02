'use client';

import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

export interface ReportColumn<T> {
  key: string;
  label: string;
  render?: (row: T) => React.ReactNode;
  sortable?: boolean;
  align?: 'left' | 'right' | 'center';
  className?: string;
}

export interface ReportTableProps<T> {
  columns: ReportColumn<T>[];
  rows: T[];
  isLoading?: boolean;
  emptyMessage?: string;
  defaultSortKey?: string;
  defaultSortDirection?: 'asc' | 'desc';
  /**
   * If provided, rows are grouped by this column with a sticky workspace
   * header. The grouping column itself is omitted from the row body so the
   * header becomes the visual anchor — matches operator workflow ("show me
   * Spout's queue").
   */
  groupBy?: string;
}

function getValue<T>(row: T, key: string): unknown {
  return key.split('.').reduce<unknown>(
    (acc, k) => (acc == null ? acc : (acc as Record<string, unknown>)[k]),
    row,
  );
}

function compareVals(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;  // nulls last
  if (b == null) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b);
  return String(a).localeCompare(String(b));
}

export function ReportTable<T>({
  columns,
  rows,
  isLoading = false,
  emptyMessage = 'No rows.',
  defaultSortKey,
  defaultSortDirection = 'desc',
  groupBy,
}: ReportTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(defaultSortKey ?? null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>(defaultSortDirection);

  const sorted = useMemo(() => {
    if (!sortKey) return rows;
    const out = [...rows];
    out.sort((a, b) => {
      const cmp = compareVals(getValue(a, sortKey), getValue(b, sortKey));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return out;
  }, [rows, sortKey, sortDir]);

  const grouped = useMemo(() => {
    if (!groupBy) return null;
    const groups = new Map<string, T[]>();
    for (const r of sorted) {
      const k = String(getValue(r, groupBy) ?? '—');
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(r);
    }
    return Array.from(groups.entries());
  }, [sorted, groupBy]);

  const visibleColumns = groupBy
    ? columns.filter((c) => c.key !== groupBy)
    : columns;

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  }

  if (isLoading) {
    return (
      <div className="rounded-md border bg-card">
        <div className="p-8 text-center text-sm text-muted-foreground">
          Loading…
        </div>
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div className="rounded-md border bg-card">
        <div className="p-8 text-center text-sm text-muted-foreground">
          {emptyMessage}
        </div>
      </div>
    );
  }

  function HeaderCell({ col }: { col: ReportColumn<T> }) {
    const sortable = col.sortable !== false;
    const isSorted = sortKey === col.key;
    const Icon = !isSorted ? ArrowUpDown : sortDir === 'asc' ? ArrowUp : ArrowDown;
    return (
      <TableHead
        className={cn(
          'text-xs uppercase tracking-wide text-muted-foreground',
          col.align === 'right' && 'text-right',
          col.align === 'center' && 'text-center',
          col.className,
        )}
      >
        {sortable ? (
          <button
            type="button"
            onClick={() => toggleSort(col.key)}
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            {col.label}
            <Icon className={cn('h-3 w-3', isSorted ? 'opacity-100' : 'opacity-30')} />
          </button>
        ) : (
          col.label
        )}
      </TableHead>
    );
  }

  function Cell({ col, row }: { col: ReportColumn<T>; row: T }) {
    const val = col.render ? col.render(row) : (getValue(row, col.key) as React.ReactNode);
    return (
      <TableCell
        className={cn(
          col.align === 'right' && 'text-right tabular-nums',
          col.align === 'center' && 'text-center',
          col.className,
        )}
      >
        {val == null || val === '' ? <span className="text-muted-foreground">—</span> : val}
      </TableCell>
    );
  }

  return (
    <div className="rounded-md border bg-card">
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow>
            {visibleColumns.map((col) => (
              <HeaderCell key={col.key} col={col} />
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {grouped
            ? grouped.map(([groupName, groupRows]) => (
                <GroupBlock
                  key={groupName}
                  name={groupName}
                  rows={groupRows}
                  columns={visibleColumns}
                  Cell={Cell}
                />
              ))
            : sorted.map((row, i) => (
                <TableRow key={i}>
                  {visibleColumns.map((col) => (
                    <Cell key={col.key} col={col} row={row} />
                  ))}
                </TableRow>
              ))}
        </TableBody>
      </Table>
    </div>
  );
}

function GroupBlock<T>({
  name,
  rows,
  columns,
  Cell,
}: {
  name: string;
  rows: T[];
  columns: ReportColumn<T>[];
  Cell: React.ComponentType<{ col: ReportColumn<T>; row: T }>;
}) {
  return (
    <>
      <TableRow className="bg-muted/60 hover:bg-muted/60">
        <TableCell
          colSpan={columns.length}
          className="py-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
        >
          {name} <span className="font-normal opacity-70">· {rows.length} row{rows.length === 1 ? '' : 's'}</span>
        </TableCell>
      </TableRow>
      {rows.map((row, i) => (
        <TableRow key={i}>
          {columns.map((col) => (
            <Cell key={col.key} col={col} row={row} />
          ))}
        </TableRow>
      ))}
    </>
  );
}
