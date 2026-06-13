import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import type { AdSlot } from "@/lib/types";

export async function GET() {
  const filePath = path.join(process.cwd(), "public/data/ad-slots.json");
  const raw = await readFile(filePath, "utf-8");
  const slots = JSON.parse(raw) as AdSlot[];
  return NextResponse.json({
    slots,
    meta: {
      total: slots.length,
      available: slots.filter((s) => s.status === "available").length,
    },
  });
}
