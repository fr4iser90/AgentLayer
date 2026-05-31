/** Mirrors tokenRefresh.ts — proactive refresh scheduling. */
function jwtExpMs(token) {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const b64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const payload = JSON.parse(Buffer.from(b64, "base64").toString("utf8"));
    const exp = payload.exp;
    return typeof exp === "number" && Number.isFinite(exp) ? exp * 1000 : null;
  } catch {
    return null;
  }
}

const ACCESS_REFRESH_BUFFER_MS = 2 * 60 * 1000;

function accessTokenNeedsRefresh(token, now = Date.now()) {
  if (!token) return false;
  const exp = jwtExpMs(token);
  if (exp == null) return false;
  return exp - now <= ACCESS_REFRESH_BUFFER_MS;
}

function msUntilProactiveRefresh(token, now = Date.now()) {
  const exp = jwtExpMs(token);
  if (exp == null) return null;
  return Math.max(0, exp - now - ACCESS_REFRESH_BUFFER_MS);
}

function assert(cond, msg) {
  if (!cond) {
    console.error("FAIL:", msg);
    process.exit(1);
  }
}

const header = Buffer.from(JSON.stringify({ alg: "none" })).toString("base64url");
const exp = Math.floor(Date.now() / 1000) + 900;
const payload = Buffer.from(JSON.stringify({ exp })).toString("base64url");
const fakeJwt = `${header}.${payload}.sig`;

assert(jwtExpMs(fakeJwt) != null, "parses exp");
assert(!accessTokenNeedsRefresh(fakeJwt), "fresh token");
assert(
  accessTokenNeedsRefresh(fakeJwt, exp * 1000 - 60_000),
  "needs refresh inside buffer"
);
assert(msUntilProactiveRefresh(fakeJwt) > 0, "positive delay");

console.log("test-token-refresh: ok");
