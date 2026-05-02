import { ReportsTabNav } from '@/components/reports/ReportsTabNav';

export default function ReportsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col">
      <header className="border-b">
        <div className="px-6 py-4">
          <h1 className="text-2xl font-semibold">Reports</h1>
          <p className="text-sm text-muted-foreground">
            Operator queues — sorted by workspace, then most recent event. Each
            report is also downloadable as CSV.
          </p>
        </div>
        <ReportsTabNav />
      </header>
      <div className="flex-1 p-6">{children}</div>
    </div>
  );
}
