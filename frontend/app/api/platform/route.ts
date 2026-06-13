import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";
import type { Activation, PlatformStats } from "@/lib/types";

export async function GET() {
  const statsPath = path.join(process.cwd(), "public/data/platform-stats.json");
  const activationsPath = path.join(
    process.cwd(),
    "public/data/activations.json"
  );
  const [statsRaw, activationsRaw] = await Promise.all([
    readFile(statsPath, "utf-8"),
    readFile(activationsPath, "utf-8"),
  ]);
  return NextResponse.json({
    stats: JSON.parse(statsRaw) as PlatformStats,
    activations: JSON.parse(activationsRaw) as Activation[],
  });
}
