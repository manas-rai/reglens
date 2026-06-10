export function SkeletonRows({
  rows = 5,
  cols = 4,
}: {
  rows?: number;
  cols?: number;
}) {
  return (
    <table className="risk-table">
      <tbody>
        {Array.from({ length: rows }).map((_, r) => (
          <tr key={r}>
            {Array.from({ length: cols }).map((_, c) => (
              <td key={c}>
                <span className="skeleton" />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
