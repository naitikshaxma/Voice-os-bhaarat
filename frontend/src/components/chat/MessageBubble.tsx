

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  confidenceLevel?: string;
  fallbackUsed?: boolean;
}

interface MessageBubbleProps {
  message: ChatMessage;
}

const MessageBubble = ({ message }: MessageBubbleProps) => {
  const isUser = message.role === 'user';

  return (
    <div className={`chat-fade-in max-w-[85%] md:max-w-[70%] ${isUser ? 'self-end' : 'self-start'}`}>
      <div
        className={`rounded-2xl px-4 py-3 border ${
          isUser
            ? 'rounded-br-md bg-[#f59e0b] text-black border-[#f59e0b]'
            : 'rounded-bl-md bg-[#171717] text-[#e5e7eb] border-[#2a2a2a]'
        }`}
      >
        <p className="text-sm md:text-base leading-relaxed whitespace-pre-wrap">{message.text}</p>
      </div>
    </div>
  );
};

export default MessageBubble;
