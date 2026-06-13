import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

// Colored 3D voxel point cloud for one wall (built by scripts/voxelize_walls.py).
// Prefer the live FastAPI backend when configured; surface a reachable 404, and
// on a network error fall back to the static JSON shipped in public/data.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const backend = process.env.BACKEND_URL;
  if (backend) {
    try {
      const res = await fetch(`${backend}/api/walls/${id}/voxels`, {
        cache: "no-store",
      });
      if (res.ok) return NextResponse.json(await res.json());
      if (res.status === 404) {
        return NextResponse.json({ error: "Voxels not found" }, { status: 404 });
      }
    } catch {
      // network/backend error — fall through to static data
    }
  }

  try {
    const filePath = path.join(
      process.cwd(),
      "public/data/wall_voxels",
      `${id}.json`
    );
    const raw = await readFile(filePath, "utf-8");
    return NextResponse.json(JSON.parse(raw));
  } catch {
    return NextResponse.json({ error: "Voxels not found" }, { status: 404 });
  }
}
