/**
 * Client-side mirror of services/parser-worker/src/parser_worker/detector.py's
 * _pair_files() — matches CA LISA-style request/response file pairs by:
 *   1. Shared timestamp suffix in filename (_20260610_100059)
 *   2. Longest common prefix after stripping Request/Response tokens
 *   3. One-to-one fallback if there's exactly one request and one response
 *
 * Kept in lockstep with the Python implementation deliberately — same regexes,
 * same scoring, same order of strategies. If the backend's algorithm changes,
 * update both.
 */

const REQUEST_FILE_RE = /[_-]?request[_-]?/gi;
const RESPONSE_FILE_RE = /[_-]?response[_-]?/gi;
const TIMESTAMP_RE = /_(\d{8}_\d{6})/;

// Content markers — mirrors parser-worker's _REQUEST_RE / _INLINE_RESPONSE_RE /
// _BARE_RESPONSE_RE / _LABELLED_RESPONSE_LABEL_RE. Label-text-agnostic: these
// search anywhere in the content, so a custom-prefixed labelled-variant label
// (e.g. "AccountInstructionsRequestHeader:") still matches via the embedded
// "={Method=" / "={StatusCode=" block regardless of what the label itself says.
const CONTENT_REQUEST_RE = /=\{Method="(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)"/;
const CONTENT_RESPONSE_RE = /ResponseHeader=\{StatusCode="|=\{StatusCode="/;

export interface NamedFile {
  name: string;
  key: string;
  /** Optional file text — when provided, content is checked before filename
   * (see isRequestFile/isResponseFile): capture tools don't always name
   * files consistently with what they contain (seen live — a file named
   * "..._Request.txt" that was pure response content). */
  content?: string;
}

export interface PairingResult<T extends NamedFile> {
  pairs: Array<{ request: T; response: T }>;
  unpaired: T[];
}

function isRequestFile(file: NamedFile): boolean {
  if (file.content !== undefined) {
    const isReq = CONTENT_REQUEST_RE.test(file.content);
    const isResp = CONTENT_RESPONSE_RE.test(file.content);
    if (isReq && !isResp) return true;
    if (isResp && !isReq) return false;
  }
  return /[_-]?request[_-]?/i.test(file.name);
}

function isResponseFile(file: NamedFile): boolean {
  if (file.content !== undefined) {
    const isReq = CONTENT_REQUEST_RE.test(file.content);
    const isResp = CONTENT_RESPONSE_RE.test(file.content);
    if (isResp && !isReq) return true;
    if (isReq && !isResp) return false;
  }
  return /[_-]?response[_-]?/i.test(file.name);
}

function commonPrefixLength(a: string, b: string): number {
  const len = Math.min(a.length, b.length);
  let i = 0;
  while (i < len && a[i] === b[i]) i++;
  return i;
}

/**
 * Classify files as request/response/other, then pair requests to responses.
 * Files that are neither classified as request nor response (e.g. a
 * self-contained Postman/OpenAPI/JSON file, or an already-combined .txt) are
 * returned untouched in `unpaired` alongside any request/response file that
 * couldn't be matched.
 */
export function pairHttpCaptureFiles<T extends NamedFile>(files: T[]): PairingResult<T> {
  // Mirrors the Python if/elif priority exactly: a name matching BOTH tokens
  // (e.g. "combined_request_response.txt" — a real filename in
  // Sample_SV_Files, already a self-contained combined file) is classified
  // as a request, not both — never split across two buckets.
  const requests: T[] = [];
  const responses: T[] = [];
  const others: T[] = [];
  for (const file of files) {
    if (isRequestFile(file)) requests.push(file);
    else if (isResponseFile(file)) responses.push(file);
    else others.push(file);
  }

  const pairs: Array<{ request: T; response: T }> = [];
  const unmatchedResponses = new Set(responses.map((r) => r.key));
  const unmatchedRequests: T[] = [];

  for (const req of requests) {
    let matched = false;

    // Strategy 1 — exact timestamp match
    const ts = TIMESTAMP_RE.exec(req.name)?.[1];
    if (ts) {
      const resp = responses.find((r) => unmatchedResponses.has(r.key) && r.name.includes(ts));
      if (resp) {
        pairs.push({ request: req, response: resp });
        unmatchedResponses.delete(resp.key);
        matched = true;
      }
    }

    // Strategy 2 — longest common prefix after stripping Request/Response tokens
    if (!matched) {
      const reqStripped = req.name.replace(REQUEST_FILE_RE, "").toLowerCase();
      let best: T | null = null;
      let bestScore = 0;
      for (const resp of responses) {
        if (!unmatchedResponses.has(resp.key)) continue;
        const respStripped = resp.name.replace(RESPONSE_FILE_RE, "").toLowerCase();
        const score = commonPrefixLength(reqStripped, respStripped);
        if (score > bestScore) {
          bestScore = score;
          best = resp;
        }
      }
      if (best && bestScore >= 4) {
        pairs.push({ request: req, response: best });
        unmatchedResponses.delete(best.key);
        matched = true;
      }
    }

    if (!matched) unmatchedRequests.push(req);
  }

  // Strategy 3 — one-to-one fallback when nothing else matched at all
  if (pairs.length === 0 && requests.length === 1 && responses.length === 1) {
    pairs.push({ request: requests[0], response: responses[0] });
    return { pairs, unpaired: others };
  }

  const unpaired = [
    ...others,
    ...unmatchedRequests,
    ...responses.filter((r) => unmatchedResponses.has(r.key)),
  ];
  return { pairs, unpaired };
}

function stripExtension(name: string): string {
  return name.replace(/\.[^.]+$/, "");
}

/**
 * Concatenate a matched request + response File into one combined File,
 * naming it so both original names' tokens survive (the response filename's
 * "Error400"/"Success" token is what the backend's CA LISA parser uses to
 * infer a templated %%StatusCode%% — see ingestion-service's upload.py).
 */
export async function mergeHttpCaptureFiles(request: File, response: File): Promise<File> {
  const [reqBytes, respBytes] = await Promise.all([request.arrayBuffer(), response.arrayBuffer()]);
  const merged = new Uint8Array(reqBytes.byteLength + 1 + respBytes.byteLength);
  merged.set(new Uint8Array(reqBytes), 0);
  merged.set(new Uint8Array([0x0a]), reqBytes.byteLength);
  merged.set(new Uint8Array(respBytes), reqBytes.byteLength + 1);
  const combinedName = `${stripExtension(request.name)}__${stripExtension(response.name)}_combined.txt`;
  return new File([merged], combinedName, { type: "text/plain" });
}
