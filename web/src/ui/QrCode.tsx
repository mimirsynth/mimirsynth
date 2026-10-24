/** Código QR a partir de un SVG ya generado por la API (se pinta como imagen, nunca como HTML). */
export function QrCode({ svg, label }: { svg: string; label: string }) {
  return <img className="ms-qr" alt={label} width={176} height={176} src={`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`} />;
}
