import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import type { VendorStall } from "@/lib/types";

export async function GET() {
  const filePath = path.join(process.cwd(), "public/data/vendor-stalls.json");
  const raw = await readFile(filePath, "utf-8");
  const stalls = JSON.parse(raw) as VendorStall[];
  return NextResponse.json({
    stalls,
    meta: {
      total: stalls.length,
      available: stalls.filter((s) => s.status === "available").length,
    },
  });
}
