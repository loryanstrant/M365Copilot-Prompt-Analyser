// Friendly empty-state banner shown when a page has no analysed data yet.
export default function EmptyState({
  show,
  className = "",
}: {
  show: boolean;
  className?: string;
}) {
  if (!show) return null;
  return (
    <div
      className={`rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-400 ${className}`}
    >
      No analysed prompts yet. Configure Microsoft Graph + Azure OpenAI in{" "}
      <span className="font-semibold">Settings</span> and run an ingest, or seed demo data.
    </div>
  );
}
