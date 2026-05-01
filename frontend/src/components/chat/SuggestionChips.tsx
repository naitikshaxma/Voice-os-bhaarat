interface SuggestionChipsProps {
  onSelect: (text: string) => void;
  disabled?: boolean;
}

const SUGGESTIONS = [
  'आवेदन कैसे करें?',
  'कितना पैसा मिलेगा?',
  'कौन से दस्तावेज चाहिए?',
];

const SuggestionChips = ({ onSelect, disabled = false }: SuggestionChipsProps) => {
  return (
    <div className="flex flex-wrap gap-2">
      {SUGGESTIONS.map((item) => (
        <button
          key={item}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(item)}
          className="px-3 py-1.5 rounded-full text-xs md:text-sm border border-[#2b2b2b] bg-[#141414] text-[#d1d5db] hover:bg-[#1e1e1e] hover:border-[#3f3f3f] transition disabled:opacity-50"
        >
          {item}
        </button>
      ))}
    </div>
  );
};

export default SuggestionChips;
