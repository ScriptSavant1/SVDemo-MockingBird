import { describe, it, expect } from "vitest";
import { pairHttpCaptureFiles, type NamedFile } from "@/lib/httpCapturePairing";

function f(name: string): NamedFile {
  return { name, key: name };
}

describe("pairHttpCaptureFiles", () => {
  it("pairs files sharing an exact timestamp suffix", () => {
    const { pairs, unpaired } = pairHttpCaptureFiles([
      f("1781082059482RTCAERv01_Request_20260610_100059.txt"),
      f("1781082059500RTCAERv01_Success1Response_20260610_100059.txt"),
    ]);
    expect(pairs).toHaveLength(1);
    expect(pairs[0].request.name).toContain("Request");
    expect(pairs[0].response.name).toContain("Success1Response");
    expect(unpaired).toHaveLength(0);
  });

  it("falls back to longest-common-prefix when timestamps differ by a second", () => {
    // The real Sample_SV_Files case: _100912 request vs _100911 response.
    const { pairs, unpaired } = pairHttpCaptureFiles([
      f("1781082552845RTCAERv01_Request_20260610_100912.txt"),
      f("1781082551676RTCAERv01_Error400Response_20260610_100911.txt"),
    ]);
    expect(pairs).toHaveLength(1);
    expect(pairs[0].response.name).toContain("Error400Response");
    expect(unpaired).toHaveLength(0);
  });

  it("pairs multiple independent request/response sets by prefix", () => {
    const { pairs, unpaired } = pairHttpCaptureFiles([
      f("CreateAdviserPOST_Request.txt"),
      f("CreateAdviserPost_Response.txt"),
      f("GetAdvisers_Request.txt"),
      f("GetAdvisersByID_Response.txt"),
    ]);
    expect(pairs).toHaveLength(2);
    expect(unpaired).toHaveLength(0);
  });

  it("falls back to one-to-one when exactly one request and one response exist with no match signal", () => {
    const { pairs } = pairHttpCaptureFiles([f("request.txt"), f("response.txt")]);
    expect(pairs).toHaveLength(1);
  });

  it("force-pairs a single request + single response even with unrelated names (matches backend fallback)", () => {
    // Mirrors _pair_files' Strategy 3 exactly: with exactly one request and
    // one response file and nothing else to go on, they're assumed to be a
    // pair — the same behavior the backend's ZIP handler already has.
    const { pairs, unpaired } = pairHttpCaptureFiles([
      f("Orphan_Request_20260610_100059.txt"),
      f("Unrelated_Response_20260611_000000.txt"),
    ]);
    expect(pairs).toHaveLength(1);
    expect(unpaired).toHaveLength(0);
  });

  it("leaves a genuinely unmatched request unpaired when more than one candidate exists", () => {
    const { pairs, unpaired } = pairHttpCaptureFiles([
      f("Payments_Request_20260610_100059.txt"),
      f("Payments_Response_20260610_100059.txt"),
      f("Orphan_Request_20260620_120000.txt"),
    ]);
    expect(pairs).toHaveLength(1);
    expect(unpaired).toEqual([f("Orphan_Request_20260620_120000.txt")]);
  });

  it("passes through non-request/response files (Postman, OpenAPI) untouched", () => {
    const { pairs, unpaired } = pairHttpCaptureFiles([f("customer-api-full.json")]);
    expect(pairs).toHaveLength(0);
    expect(unpaired).toEqual([f("customer-api-full.json")]);
  });

  it("treats an already-combined file (matches both tokens) as unpaired, not silently mismatched", () => {
    // "combined_request_response.txt" is a real Sample_SV_Files filename —
    // already self-contained. It should pass through standalone, not get
    // force-paired with something else just because it contains "request".
    const { pairs, unpaired } = pairHttpCaptureFiles([f("combined_request_response.txt")]);
    expect(pairs).toHaveLength(0);
    expect(unpaired).toEqual([f("combined_request_response.txt")]);
  });

  it("handles a mix of pairable halves and standalone files in one batch", () => {
    const { pairs, unpaired } = pairHttpCaptureFiles([
      f("Payments_Request_20260610_100059.txt"),
      f("Payments_Response_20260610_100059.txt"),
      f("postman-collection.json"),
    ]);
    expect(pairs).toHaveLength(1);
    expect(unpaired).toEqual([f("postman-collection.json")]);
  });
});
