import { NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/middleware";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const password = process.env.SITE_PASSWORD ?? process.env.GENERATE_PASSWORD;
  if (!password) {
    return NextResponse.json({ error: "No password configured." }, { status: 501 });
  }

  let body: { password?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Bad request." }, { status: 400 });
  }

  if (body.password !== password) {
    return NextResponse.json({ error: "Wrong password." }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set(AUTH_COOKIE, password, {
    httpOnly: true,
    sameSite: "lax",
    secure: true,
    path: "/",
    // A year: this is a reading app opened daily on a phone, and being asked
    // again every fortnight would be the whole cost of the feature.
    maxAge: 60 * 60 * 24 * 365,
  });
  return res;
}
