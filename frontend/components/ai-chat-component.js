/**
 * Reusable AI Chat Component
 * Can be used across all SEO tools pages
 */
class AIChatComponent {
    constructor(containerId, options = {}) {
        this.containerId = containerId;
        this.options = {
            context: 'general',
            chatHistoryKey: 'aiChatHistory',
            placeholder: 'Ask me anything about SEO...',
            ...options
        };
        
        this.chatHistory = [];
        this.currentAnalysis = null;
        this.currentDomain = null;
        
        this.init();
    }
    
    init() {
        this.createChatHTML();
        this.loadChatHistory();
        this.bindEvents();
    }
    
    createChatHTML() {
        const container = document.getElementById(this.containerId);
        if (!container) {
            console.error(`Container with ID '${this.containerId}' not found`);
            return;
        }
        
        container.innerHTML = `
            <div class="ai-chat-container">
                <div class="chat-header">
                    <h3><i class="fas fa-robot"></i> AI Assistant</h3>
                    <p>Get expert SEO advice and recommendations</p>
                </div>
                
                <div class="chat-messages" id="${this.containerId}-messages">
                    <div class="message ai">
                        <div class="message-avatar">AI</div>
                        <div class="message-content">
                            Hello! I'm your AI SEO assistant. I can help you with technical SEO, keyword research, competitor analysis, backlink strategies, and content planning. How can I help you today?
                        </div>
                    </div>
                </div>
                
                <div class="typing-indicator" id="${this.containerId}-typing" style="display: none;">
                    <div class="message-avatar">AI</div>
                    <div class="message-content">
                        <span>AI is typing</span>
                        <div class="typing-dots">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </div>
                </div>
                
                <div class="chat-input">
                    <input type="text" id="${this.containerId}-input" placeholder="${this.options.placeholder}" />
                    <button id="${this.containerId}-send" onclick="aiChatComponent.sendMessage()">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        `;
        
        this.addChatStyles();
    }
    
    addChatStyles() {
        const styleId = `${this.containerId}-styles`;
        if (document.getElementById(styleId)) return;
        
        const style = document.createElement('style');
        style.id = styleId;
        style.textContent = `
            .ai-chat-container {
                background: white;
                border-radius: 12px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                overflow: hidden;
                height: 500px;
                display: flex;
                flex-direction: column;
            }
            
            .chat-header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 1rem;
                text-align: center;
            }
            
            .chat-header h3 {
                margin: 0 0 0.5rem 0;
                font-size: 1.1rem;
                font-weight: 600;
            }
            
            .chat-header p {
                margin: 0;
                font-size: 0.85rem;
                opacity: 0.9;
            }
            
            .chat-messages {
                flex: 1;
                padding: 1rem;
                overflow-y: auto;
                background: #f8fafc;
            }
            
            .message {
                display: flex;
                margin-bottom: 1rem;
                gap: 0.75rem;
            }
            
            .message-avatar {
                width: 32px;
                height: 32px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 0.75rem;
                font-weight: 600;
                flex-shrink: 0;
            }
            
            .message.user .message-avatar {
                background: #667eea;
                color: white;
            }
            
            .message.ai .message-avatar {
                background: #e2e8f0;
                color: #64748b;
            }
            
            .message-content {
                flex: 1;
                padding: 0.75rem 1rem;
                border-radius: 8px;
                max-width: 70%;
            }
            
            .message.user .message-content {
                background: #667eea;
                color: white;
            }
            
            .message.ai .message-content {
                background: white;
                border: 1px solid #e2e8f0;
            }
            
            /* Enhanced formatting for AI responses */
            .message-content strong {
                font-weight: 600;
                color: #1e293b;
            }
            
            .message-content em {
                font-style: italic;
                color: #64748b;
            }
            
            .message-content code {
                background: #f1f5f9;
                padding: 2px 6px;
                border-radius: 4px;
                font-family: 'Courier New', monospace;
                font-size: 13px;
                color: #e11d48;
            }
            
            .message-content pre {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 12px;
                margin: 8px 0;
                overflow-x: auto;
            }
            
            .message-content pre code {
                background: none;
                padding: 0;
                color: #334155;
            }
            
            .message-content ul {
                margin: 8px 0;
                padding-left: 20px;
            }
            
            .message-content li {
                margin: 4px 0;
                line-height: 1.6;
            }
            
            .message-content h3 {
                font-size: 16px;
                font-weight: 600;
                color: #1e293b;
                margin: 12px 0 8px 0;
                padding-bottom: 4px;
                border-bottom: 1px solid #e2e8f0;
            }
            
            .message-content h4 {
                font-size: 14px;
                font-weight: 600;
                color: #374151;
                margin: 10px 0 6px 0;
            }
            
            .message-content br {
                margin: 4px 0;
            }
            
            .typing-indicator {
                display: flex;
                padding: 1rem;
                gap: 0.75rem;
                background: #f8fafc;
            }
            
            .typing-dots {
                display: flex;
                gap: 4px;
                margin-left: 8px;
            }
            
            .typing-dots span {
                width: 6px;
                height: 6px;
                background: #666;
                border-radius: 50%;
                animation: typing 1.4s infinite;
            }
            
            .typing-dots span:nth-child(2) {
                animation-delay: 0.2s;
            }
            
            .typing-dots span:nth-child(3) {
                animation-delay: 0.4s;
            }
            
            @keyframes typing {
                0%, 60%, 100% {
                    transform: translateY(0);
                }
                30% {
                    transform: translateY(-10px);
                }
            }
            
            .chat-input {
                display: flex;
                padding: 1rem;
                border-top: 1px solid #e2e8f0;
                background: white;
            }
            
            .chat-input input {
                flex: 1;
                padding: 0.75rem;
                border: 1px solid #e2e8f0;
                border-radius: 8px 0 0 8px;
                font-size: 0.9rem;
                outline: none;
            }
            
            .chat-input input:focus {
                border-color: #667eea;
            }
            
            .chat-input button {
                padding: 0.75rem 1rem;
                background: #667eea;
                color: white;
                border: none;
                border-radius: 0 8px 8px 0;
                cursor: pointer;
                font-size: 0.9rem;
                transition: background 0.2s;
            }
            
            .chat-input button:hover {
                background: #5a6fd8;
            }
            
            .chat-input button:disabled {
                background: #cbd5e1;
                cursor: not-allowed;
            }
        `;
        
        document.head.appendChild(style);
    }
    
    bindEvents() {
        const input = document.getElementById(`${this.containerId}-input`);
        const sendBtn = document.getElementById(`${this.containerId}-send`);
        
        if (input) {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    this.sendMessage();
                }
            });
        }
        
        if (sendBtn) {
            sendBtn.addEventListener('click', () => {
                this.sendMessage();
            });
        }
    }
    
    async sendMessage() {
        const input = document.getElementById(`${this.containerId}-input`);
        const sendBtn = document.getElementById(`${this.containerId}-send`);
        const typingIndicator = document.getElementById(`${this.containerId}-typing`);
        
        if (!input || !sendBtn) return;
        
        const message = input.value.trim();
        if (!message) return;
        
        // Add user message
        this.addMessage('user', message);
        
        // Clear input and disable send button
        input.value = '';
        sendBtn.disabled = true;
        sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        
        // Show typing indicator
        if (typingIndicator) {
            typingIndicator.style.display = 'flex';
        }
        
        try {
            const response = await fetch('/api/ai/mozarex-chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    context: this.options.context,
                    analysis: this.currentAnalysis,
                    domain: this.currentDomain
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.addMessage('ai', data.response);
            } else {
                this.addMessage('ai', 'Sorry, I encountered an error. Please try again.');
            }
        } catch (error) {
            console.error('Error sending message:', error);
            this.addMessage('ai', 'Sorry, I encountered an error. Please try again.');
        } finally {
            // Hide typing indicator and re-enable send button
            if (typingIndicator) {
                typingIndicator.style.display = 'none';
            }
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
        }
    }
    
    addMessage(sender, message) {
        const messagesContainer = document.getElementById(`${this.containerId}-messages`);
        if (!messagesContainer) return;
        
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}`;
        
        const avatar = sender === 'user' ? 'U' : 'AI';
        
        // Process message for formatting (only for AI responses)
        let processedMessage = message;
        if (sender === 'ai') {
            processedMessage = this.formatAIResponse(message);
        }
        
        messageElement.innerHTML = `
            <div class="message-avatar">${avatar}</div>
            <div class="message-content">${processedMessage}</div>
        `;
        
        messagesContainer.appendChild(messageElement);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
        
        // Save to chat history
        this.chatHistory.push({ sender, message, timestamp: new Date().toISOString() });
        localStorage.setItem(this.options.chatHistoryKey, JSON.stringify(this.chatHistory));
    }
    
    formatAIResponse(message) {
        // Convert markdown-like formatting to HTML
        let formatted = message;
        
        // Handle line breaks
        formatted = formatted.replace(/\n/g, '<br>');
        
        // Handle bold text (**text**)
        formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Handle italic text (*text*)
        formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Handle code blocks (```code```)
        formatted = formatted.replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>');
        
        // Handle inline code (`code`)
        formatted = formatted.replace(/`(.*?)`/g, '<code>$1</code>');
        
        // Handle lists (- item)
        formatted = formatted.replace(/^- (.*$)/gm, '<li>$1</li>');
        formatted = formatted.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
        
        // Handle numbered lists (1. item)
        formatted = formatted.replace(/^\d+\. (.*$)/gm, '<li>$1</li>');
        
        // Handle headers (## Header)
        formatted = formatted.replace(/^## (.*$)/gm, '<h3>$1</h3>');
        formatted = formatted.replace(/^### (.*$)/gm, '<h4>$1</h4>');
        
        // Handle emojis and special characters
        formatted = formatted.replace(/✅/g, '<span style="color: #22c55e;">✅</span>');
        formatted = formatted.replace(/❌/g, '<span style="color: #ef4444;">❌</span>');
        formatted = formatted.replace(/⚠️/g, '<span style="color: #f59e0b;">⚠️</span>');
        formatted = formatted.replace(/📝/g, '<span style="color: #3b82f6;">📝</span>');
        formatted = formatted.replace(/🔍/g, '<span style="color: #8b5cf6;">🔍</span>');
        formatted = formatted.replace(/💡/g, '<span style="color: #f59e0b;">💡</span>');
        formatted = formatted.replace(/🎯/g, '<span style="color: #ef4444;">🎯</span>');
        formatted = formatted.replace(/📊/g, '<span style="color: #06b6d4;">📊</span>');
        formatted = formatted.replace(/🚀/g, '<span style="color: #10b981;">🚀</span>');
        formatted = formatted.replace(/👉/g, '<span style="color: #6366f1;">👉</span>');
        formatted = formatted.replace(/📈/g, '<span style="color: #059669;">📈</span>');
        formatted = formatted.replace(/🔧/g, '<span style="color: #7c3aed;">🔧</span>');
        formatted = formatted.replace(/⭐/g, '<span style="color: #f59e0b;">⭐</span>');
        formatted = formatted.replace(/📋/g, '<span style="color: #3b82f6;">📋</span>');
        formatted = formatted.replace(/🎨/g, '<span style="color: #ec4899;">🎨</span>');
        formatted = formatted.replace(/🏠/g, '<span style="color: #059669;">🏠</span>');
        formatted = formatted.replace(/🚨/g, '<span style="color: #dc2626;">🚨</span>');
        formatted = formatted.replace(/🔴/g, '<span style="color: #dc2626;">🔴</span>');
        formatted = formatted.replace(/🟡/g, '<span style="color: #f59e0b;">🟡</span>');
        formatted = formatted.replace(/🟢/g, '<span style="color: #22c55e;">🟢</span>');
        formatted = formatted.replace(/🏆/g, '<span style="color: #f59e0b;">🏆</span>');
        formatted = formatted.replace(/🔗/g, '<span style="color: #3b82f6;">🔗</span>');
        
        return formatted;
    }
    
    loadChatHistory() {
        try {
            const saved = localStorage.getItem(this.options.chatHistoryKey);
            if (saved) {
                this.chatHistory = JSON.parse(saved);
                this.displayChatHistory();
            }
        } catch (error) {
            console.error('Error loading chat history:', error);
            this.chatHistory = [];
        }
    }
    
    displayChatHistory() {
        const messagesContainer = document.getElementById(`${this.containerId}-messages`);
        if (!messagesContainer) return;
        
        // Clear existing messages except the welcome message
        messagesContainer.innerHTML = `
            <div class="message ai">
                <div class="message-avatar">AI</div>
                <div class="message-content">
                    Hello! I'm your AI SEO assistant. I can help you with technical SEO, keyword research, competitor analysis, backlink strategies, and content planning. How can I help you today?
                </div>
            </div>
        `;
        
        // Add chat history
        this.chatHistory.forEach(chat => {
            this.addMessage(chat.sender, chat.message);
        });
    }
    
    // Public methods for external use
    setAnalysis(analysis) {
        this.currentAnalysis = analysis;
    }
    
    setDomain(domain) {
        this.currentDomain = domain;
    }
    
    setContext(context) {
        this.options.context = context;
    }
    
    clearHistory() {
        this.chatHistory = [];
        localStorage.removeItem(this.options.chatHistoryKey);
        this.displayChatHistory();
    }
    
    addQuickAction(actionText, callback) {
        // This can be extended to add quick action buttons
        console.log('Quick action:', actionText);
        if (callback) callback();
    }
}

// Global instance for easy access
let aiChatComponent = null;

// Initialize function
function initAIChat(containerId, options = {}) {
    aiChatComponent = new AIChatComponent(containerId, options);
    return aiChatComponent;
}
