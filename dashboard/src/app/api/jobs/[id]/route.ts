import { getJob } from "@/lib/server/anamika";
import { handle, safeJob } from "@/lib/server/route";

export const dynamic = "force-dynamic";

export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const id = safeJob((await ctx.params).id);
  return handle(async () => {
    if (!id) throw new Error("bad_job");
    return getJob(id);
  });
}
