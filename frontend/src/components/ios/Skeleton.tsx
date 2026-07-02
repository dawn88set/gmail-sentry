import { cn } from '@/lib/utils';

/**
 * Ghost/skeleton loading placeholders — a shimmering block that mimics the shape
 * of the real content so pages don't flash a bare "Loading…" spinner. Use the
 * shared row inside a `ListGroup variant="plain-mobile"` so it lines up 1:1 with
 * the loaded list rows (inbox alerts, category messages, filing rules, …).
 */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-md bg-muted', className)} />;
}

/** One ghost list row: avatar circle + two text lines. */
export function SkeletonRow() {
  return (
    <div className="flex items-start gap-3 px-4 py-3.5">
      <Skeleton className="mt-0.5 h-9 w-9 flex-shrink-0 rounded-full" />
      <div className="min-w-0 flex-1 space-y-2 py-0.5">
        <Skeleton className="h-3.5 w-1/2" />
        <Skeleton className="h-3 w-4/5" />
      </div>
    </div>
  );
}

/** `count` ghost rows — drop straight into a ListGroup while data loads. */
export function SkeletonRows({ count = 5 }: { count?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </>
  );
}
