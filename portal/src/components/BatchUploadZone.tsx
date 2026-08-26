import { useRef, type DragEvent, type ChangeEvent } from "react";
import { clsx } from "clsx";

// Format is detected server-side from content, not extension — this list only
// controls what the browser's file picker shows/allows.
const ACCEPTED_EXTENSIONS = [".txt", ".json", ".xml"];

export interface BatchFile {
  file: File;
  key: string;
}

interface BatchUploadZoneProps {
  files: BatchFile[];
  onChange: (files: BatchFile[]) => void;
  disabled?: boolean;
}

export function BatchUploadZone({ files, onChange, disabled }: BatchUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  function addFiles(incoming: File[]) {
    const accepted = incoming.filter((f) => isAccepted(f.name));
    const existingKeys = new Set(files.map((f) => f.key));
    const additions = accepted
      .map((file) => ({ file, key: `${file.name}:${file.size}:${file.lastModified}` }))
      .filter((f) => !existingKeys.has(f.key));
    if (additions.length > 0) onChange([...files, ...additions]);
  }

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    addFiles(Array.from(e.dataTransfer.files));
  }

  function handleInputChange(e: ChangeEvent<HTMLInputElement>) {
    addFiles(Array.from(e.target.files ?? []));
    e.target.value = "";
  }

  function removeAt(key: string) {
    onChange(files.filter((f) => f.key !== key));
  }

  return (
    <div className="space-y-3">
      <div
        role="button"
        aria-label="Multi-file drop zone"
        tabIndex={0}
        onDragEnter={(e) => { e.preventDefault(); e.stopPropagation(); }}
        onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
        onDrop={handleDrop}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && !disabled && inputRef.current?.click()}
        data-testid="batch-upload-zone"
        className={clsx(
          "flex min-h-36 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
          "border-gray-300 bg-gray-50 hover:border-[#003875] hover:bg-gray-100",
          disabled && "pointer-events-none opacity-50",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          onChange={handleInputChange}
          disabled={disabled}
          data-testid="batch-file-input"
        />
        <span className="text-3xl text-gray-400">⇈</span>
        <p className="mt-2 text-sm font-medium text-gray-700">
          Drop multiple spec files here, or click to browse
        </p>
        <p className="mt-1 text-xs text-gray-400">
          .txt / .xml (REST or SOAP HTTP pairs) · .json (Postman v2.1)
        </p>
      </div>

      {files.length > 0 && (
        <ul className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white">
          {files.map(({ file, key }) => (
            <li key={key} className="flex items-center justify-between gap-3 px-3 py-2 text-sm">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-gray-800">{file.name}</p>
                <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
              <button
                type="button"
                onClick={() => removeAt(key)}
                disabled={disabled}
                className="shrink-0 text-xs text-gray-400 underline hover:text-red-500 disabled:pointer-events-none"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function isAccepted(filename: string): boolean {
  const lower = filename.toLowerCase();
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext));
}
