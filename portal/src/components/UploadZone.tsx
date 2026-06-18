import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { clsx } from "clsx";

const ACCEPTED_EXTENSIONS = [".txt", ".json"];
const ACCEPTED_FORMATS = ".txt (HTTP pairs), .json (Postman v2.1)";

interface UploadZoneProps {
  file: File | null;
  onChange: (file: File | null) => void;
  disabled?: boolean;
}

export function UploadZone({ file, onChange, disabled }: UploadZoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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
    const dropped = e.dataTransfer.files[0] ?? null;
    if (dropped && isAccepted(dropped.name)) onChange(dropped);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    onChange(selected);
  }

  return (
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
        onChange={handleChange}
        disabled={disabled}
        data-testid="file-input"
      />

      {file ? (
        <>
          <span className="text-2xl">✓</span>
          <p className="mt-1 font-medium text-green-700">{file.name}</p>
          <p className="mt-0.5 text-xs text-green-600">
            {(file.size / 1024).toFixed(1)} KB
          </p>
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onChange(null); }}
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
          <p className="mt-1 text-xs text-gray-400">{ACCEPTED_FORMATS}</p>
        </>
      )}
    </div>
  );
}

function isAccepted(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}
