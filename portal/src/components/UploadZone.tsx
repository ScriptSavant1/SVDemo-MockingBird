import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { clsx } from "clsx";
import { mergeHttpCaptureFiles } from "@/lib/httpCapturePairing";

// Format is detected server-side from content, not extension — this list only
// controls what the browser's file picker shows/allows.
const ACCEPTED_EXTENSIONS = [".txt", ".json", ".xml"];

interface UploadZoneProps {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}

export function UploadZone({ file, onChange, disabled }: UploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  // Second file slot — for CA LISA request + response as separate .txt files
  const [secondFile, setSecondFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const secondInputRef = useRef<HTMLInputElement>(null);

  function handleDrag(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") setDragActive(true);
    if (e.type === "dragleave") setDragActive(false);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const files = Array.from(e.dataTransfer.files).filter((f) => isAccepted(f.name));
    if (files.length >= 2) {
      void mergeAndEmit(files[0], files[1]);
    } else if (files.length === 1) {
      if (!file) {
        onChange(files[0]);
      } else {
        void mergeAndEmit(file, files[0]);
      }
    }
  }

  function handleFirstChange(e: ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    onChange(selected);
    if (!selected) setSecondFile(null);
  }

  function handleSecondChange(e: ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setSecondFile(selected);
    if (selected && file) {
      void mergeAndEmit(file, selected);
    }
  }

  async function mergeAndEmit(req: File, resp: File) {
    onChange(await mergeHttpCaptureFiles(req, resp));
    setSecondFile(resp);
  }

  const isCombined = file !== null && secondFile !== null;

  return (
    <div className="space-y-3">
      {/* Primary drop zone */}
      <div
        role="button"
        aria-label="File drop zone"
        tabIndex={0}
        onDragEnter={handleDrag}
        onDragOver={handleDrag}
        onDragLeave={handleDrag}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && !disabled && inputRef.current?.click()}
        data-testid="upload-zone"
        className={clsx(
          "flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
          dragActive
            ? "border-[#00A9E0] bg-blue-50"
            : file
              ? "border-green-400 bg-green-50"
              : "border-gray-300 bg-gray-50 hover:border-[#003875] hover:bg-gray-100",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={handleFirstChange}
          disabled={disabled}
          data-testid="file-input"
        />

        {file ? (
          <>
            <span className="text-2xl">{isCombined ? "⊕" : "✓"}</span>
            <p className="mt-1 font-medium text-green-700">
              {isCombined ? "Combined: " + file.name : file.name}
            </p>
            <p className="mt-0.5 text-xs text-green-600">
              {(file.size / 1024).toFixed(1)} KB
            </p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onChange(null); setSecondFile(null); }}
              className="mt-2 text-xs text-gray-400 underline hover:text-red-500"
            >
              Remove
            </button>
          </>
        ) : (
          <>
            <span className="text-3xl text-gray-400">↑</span>
            <p className="mt-2 text-sm font-medium text-gray-700">
              Drop your spec file here, or click to browse
            </p>
            <p className="mt-1 text-xs text-gray-400">
              .txt / .xml (HTTP pairs, REST or SOAP) · .json (Postman v2.1)
            </p>
          </>
        )}
      </div>

      {/* Second file slot — only shown once a raw HTTP-capture file is selected
          (not a self-contained Postman/OpenAPI .json, which doesn't need pairing) */}
      {file && !file.name.toLowerCase().endsWith(".json") && !isCombined && (
        <div
          className={clsx(
            "rounded-lg border-2 border-dashed px-4 py-4 text-center transition-colors",
            "border-gray-200 bg-gray-50 hover:border-[#003875] hover:bg-gray-100 cursor-pointer",
            disabled && "pointer-events-none opacity-50",
          )}
          role="button"
          tabIndex={0}
          onClick={() => !disabled && secondInputRef.current?.click()}
          onKeyDown={(e) => e.key === "Enter" && !disabled && secondInputRef.current?.click()}
        >
          <input
            ref={secondInputRef}
            type="file"
            accept=".txt,.xml"
            className="hidden"
            onChange={handleSecondChange}
            disabled={disabled}
            data-testid="file-input-2"
          />
          <p className="text-xs text-gray-500">
            <span className="font-medium text-[#003875]">+ Add response file</span>
            {" "}— if your captured request and response (REST or SOAP) are in separate files, add the second one here to auto-combine them.
          </p>
        </div>
      )}

      {isCombined && (
        <p className="text-xs text-green-700">
          Request ({(secondFile as File | null) ? "req" : ""}) + response files automatically combined before upload.
        </p>
      )}
    </div>
  );
}

function isAccepted(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}
