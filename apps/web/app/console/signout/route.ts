import { NextResponse, type NextRequest } from "next/server";
import { consoleServerClient } from "@/lib/supabase/server";

export async function POST(request: NextRequest) {
  await consoleServerClient().auth.signOut();
  return NextResponse.redirect(new URL("/console/login", request.url), { status: 303 });
}
