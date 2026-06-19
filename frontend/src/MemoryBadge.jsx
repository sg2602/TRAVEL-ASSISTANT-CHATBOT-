export default function MemoryBadge({ count = 0 }) {
  if (count === 0) return null;
  return <span className="memory-badge">{count}</span>;
}
