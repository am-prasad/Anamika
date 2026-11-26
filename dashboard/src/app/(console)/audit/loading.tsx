import { Skeleton } from "@/components/ui/Skeleton";

export default function Loading() {
  return (
    <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-6">
      <Skeleton className="h-10 w-80" />
      <Skeleton className="h-5 w-[48ch]" />
      <div className="grid grid-cols-12 gap-6">
        <Skeleton className="col-span-8 h-[420px]" />
        <Skeleton className="col-span-4 h-[420px]" />
      </div>
    </div>
  );
}
