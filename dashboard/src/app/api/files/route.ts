import { listFiles } from "@/lib/server/anamika";
import { handle, safeJob } from "@/lib/server/route";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const id = safeJob(new URL(req.url).searchParams.get("job"));
  return handle(async () => {
    if (!id) throw new Error("bad_job");
    return listFiles(id);
  });
}
