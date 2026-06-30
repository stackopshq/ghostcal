import { NextRequest, NextResponse } from "next/server";

// Per-request Content-Security-Policy with a nonce, so production needs no 'unsafe-inline' in
// script-src — an XSS can't run inline script to read the zero-knowledge keys in sessionStorage.
// In development React/Next need eval + inline, which isn't a security boundary, so we relax there.
// Framing is denied everywhere except the public booking widget (/embed), which is meant to be
// embedded on third-party sites.
export function middleware(request: NextRequest) {
  const isDev = process.env.NODE_ENV !== "production";
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const isEmbed = request.nextUrl.pathname.startsWith("/embed");

  const scriptSrc = isDev
    ? "'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval'"
    : `'self' 'nonce-${nonce}' 'strict-dynamic' 'wasm-unsafe-eval'`;

  const csp = [
    "default-src 'self'",
    `script-src ${scriptSrc}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    `frame-ancestors ${isEmbed ? "*" : "'none'"}`,
  ].join("; ");

  // Pass the nonce + CSP on the request so Next applies the nonce to its own scripts; set the CSP
  // on the response so the browser enforces it.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  // Run on pages, not on Next's static assets or the image optimizer.
  matcher: [{ source: "/((?!_next/static|_next/image|favicon.ico).*)" }],
};
