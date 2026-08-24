import { zipSync } from "fflate";

/**
 * Build a real .zip File from a set of raw files, preserving their original
 * names exactly. Used by batch upload's "one stub for all files" mode:
 * the backend's ZIP-upload path (parser_worker/detector.py's
 * _detect_and_parse_zip + _pair_files) already knows how to classify
 * *_Request_*.txt / *_Response_*.txt files by name, pair them (timestamp
 * match, then filename-prefix match), and parse each pair into its own
 * ParsedStub -- all bundled into ONE Stub record with multiple WireMock
 * mappings. That's the same mechanism a manually-zipped upload already
 * uses; this just builds the zip in the browser instead of asking the user
 * to do it themselves.
 *
 * Deliberately does NOT reuse the client-side pairHttpCaptureFiles/
 * mergeHttpCaptureFiles helpers here -- those produce one stub per pair,
 * which is the opposite of what this mode is for. The backend's pairing
 * logic runs entirely server-side once the zip arrives.
 */
export async function zipHttpCaptureFiles(files: File[], zipName: string): Promise<File> {
  const entries: Record<string, Uint8Array> = {};
  for (const file of files) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    entries[file.name] = bytes;
  }
  const zipped = zipSync(entries, { level: 6 });
  return new File([zipped], zipName.endsWith(".zip") ? zipName : `${zipName}.zip`, {
    type: "application/zip",
  });
}
