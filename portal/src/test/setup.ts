import "@testing-library/jest-dom";

// jsdom doesn't implement the Pointer Events APIs Radix UI primitives
// (Tabs, Dialog, DropdownMenu, ...) rely on for click/focus handling.
// Without these, Radix's internal pointer handlers throw and interactions
// silently no-op in tests. This is the standard Radix + jsdom + Vitest shim.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.setPointerCapture) {
  Element.prototype.setPointerCapture = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom's Blob/File implementation doesn't implement .arrayBuffer() (a real
// Web API browsers support natively). UploadZone's request/response file
// merge relies on it. Polyfilled via FileReader, which jsdom does support.
if (typeof Blob !== "undefined" && !Blob.prototype.arrayBuffer) {
  Blob.prototype.arrayBuffer = function (this: Blob): Promise<ArrayBuffer> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(this);
    });
  };
}
