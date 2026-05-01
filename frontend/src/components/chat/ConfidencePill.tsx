interface ConfidencePillProps {
  level?: string;
  fallbackUsed?: boolean;
}

const ConfidencePill = ({ level, fallbackUsed }: ConfidencePillProps) => {
  const normalized = (level || 'low').toLowerCase();

  // Only show a visual indicator for HIGH and MEDIUM confidence.
  // Low confidence / fallback responses just show the text — no noisy badge.
  if (normalized === 'low' || !level) return null;

  const styleMap: Record<string, string> = {
    high: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    medium: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  };
  const labelMap: Record<string, string> = {
    high: '✓ High confidence',
    medium: '~ Medium confidence',
  };

  const styleClass = styleMap[normalized];
  const label = labelMap[normalized];
  if (!styleClass) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 mt-1">
      <span className={`text-[10px] px-2 py-0.5 rounded-full border ${styleClass}`}>
        {label}
      </span>
    </div>
  );
};

export default ConfidencePill;
