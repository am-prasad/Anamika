import { compareDoc } from "@/lib/server/anamika";
import { handle, safeJob } from "@/lib/server/route";

export const dynamic = "force-dynamic";

/** Original + sanitised text + value-free spans for one file (demo datasets only). */
export async function GET(req: Request) {
  const q = new URL(req.url).searchParams;
  const id = safeJob(q.get("job"));
  const path = q.get("path") ?? "";
  return handle(async () => {
    if (!id || !path || path.includes("..") || path.length > 400) throw new Error("bad_request");
    return compareDoc(id, path);
  });
}
