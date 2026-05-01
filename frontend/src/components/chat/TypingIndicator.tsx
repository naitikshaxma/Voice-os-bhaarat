const TypingIndicator = () => {
  return (
    <div className="chat-fade-in max-w-[85%] md:max-w-[70%] self-start rounded-2xl rounded-bl-md bg-[#171717] border border-[#2a2a2a] px-4 py-3">
      <p className="text-xs text-[#9ca3af] mb-1">AI is thinking...</p>
      <div className="typing-dots">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
};

export default TypingIndicator;
