"use client";

/**
 * Re-encode a photo through a canvas in the browser (spec J1). The canvas keeps only pixels, so
 * EXIF, GPS, camera model and XMP are all dropped. Orientation is applied first so the photo
 * still looks right. Optionally blurs detected faces (when the browser has a FaceDetector).
 */
export type Cleaned = { blob: Blob; previewUrl: string; facesBlurred: boolean; facesFound: number };

type FaceBox = { boundingBox: DOMRectReadOnly };
type FaceDetectorCtor = new (o?: { fastMode?: boolean; maxDetectedFaces?: number }) => { detect: (src: CanvasImageSource) => Promise<FaceBox[]> };

export function faceDetectionAvailable(): boolean {
  return typeof window !== "undefined" && "FaceDetector" in window;
}

export async function cleanImage(file: File, blurFaces: boolean, maxSide = 2560): Promise<Cleaned> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const w = Math.round(bitmap.width * scale), h = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();

  let facesFound = 0;
  let facesBlurred = false;
  if (blurFaces && faceDetectionAvailable()) {
    const FD = (window as unknown as { FaceDetector: FaceDetectorCtor }).FaceDetector;
    const faces = await new FD({ fastMode: true, maxDetectedFaces: 20 }).detect(canvas);
    facesFound = faces.length;
    for (const f of faces) {
      const b = f.boundingBox;
      const pad = Math.max(b.width, b.height) * 0.25;
      const x = Math.max(0, b.x - pad), y = Math.max(0, b.y - pad);
      const bw = Math.min(w - x, b.width + 2 * pad), bh = Math.min(h - y, b.height + 2 * pad);
      ctx.save();
      ctx.filter = `blur(${Math.max(12, Math.round(bw / 6))}px)`;
      ctx.drawImage(canvas, x, y, bw, bh, x, y, bw, bh);
      ctx.restore();
    }
    facesBlurred = true;
  }

  const blob = await new Promise<Blob>((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej(new Error("encode failed"))), "image/jpeg", 0.88));
  return { blob, previewUrl: URL.createObjectURL(blob), facesBlurred, facesFound };
}
