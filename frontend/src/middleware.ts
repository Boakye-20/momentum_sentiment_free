import { NextRequest, NextResponse } from "next/server";

// Attaches the backend API key to every /api/* call.
//
// This runs server-side only, so API_SECRET_KEY is never bundled into the
// browser JS — the key must NOT be prefixed NEXT_PUBLIC_, or Next.js would
// inline it into the client bundle and publish it to every visitor.
//
// The rewrite lives here rather than in next.config.ts because config
// rewrites cannot attach headers.
export function middleware(request: NextRequest) {
  const backend = process.env.API_URL ?? "http://127.0.0.1:8000";
  const key = process.env.API_SECRET_KEY ?? "";

  const url = new URL(
    request.nextUrl.pathname + request.nextUrl.search,
    backend,
  );

  const headers = new Headers(request.headers);
  if (key) headers.set("authorization", `Bearer ${key}`);

  return NextResponse.rewrite(url, { request: { headers } });
}

export const config = {
  matcher: "/api/:path*",
};
