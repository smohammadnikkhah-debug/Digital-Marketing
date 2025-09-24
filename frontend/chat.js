// AI Chat Interface JavaScript
class AIChatInterface {
    constructor() {
        this.socket = io();
        this.userId = this.generateUserId();
        this.isAnalyzing = false;
        
        this.initializeElements();
        this.setupEventListeners();
        this.setupSocketListeners();
    }

    generateUserId() {
        return 'user_' + Math.random().toString(36).substr(2, 9);
    }

    initializeElements() {
        this.chatForm = document.getElementById('chatForm');
        this.messageInput = document.getElementById('messageInput');
        this.sendButton = document.getElementById('sendButton');
        this.chatMessages = document.getElementById('chatMessages');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.websiteInput = document.getElementById('websiteInput');
        this.analyzeButton = document.getElementById('analyzeButton');
        this.clearHistoryButton = document.getElementById('clearHistory');
        this.websiteUrlInput = document.getElementById('websiteUrlInput');
        this.analyzeBtn = document.getElementById('analyzeBtn');
    }

    setupEventListeners() {
        // Chat form submission
        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });

        // Quick action buttons
        document.querySelectorAll('.quick-action[data-action]').forEach(button => {
            button.addEventListener('click', (e) => {
                const action = e.target.getAttribute('data-action');
                this.handleQuickAction(action);
            });
        });

        // Website analysis
        this.analyzeButton.addEventListener('click', () => {
            this.analyzeWebsite();
        });

        // Clear history
        this.clearHistoryButton.addEventListener('click', () => {
            this.clearHistory();
        });

        // Enter key in website input
        this.websiteInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.analyzeWebsite();
            }
        });

        // New website URL input for chat
        this.analyzeBtn.addEventListener('click', () => {
            this.analyzeWebsiteUrl();
        });

        // Enter key in new website URL input
        this.websiteUrlInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.analyzeWebsiteUrl();
            }
        });
    }

    setupSocketListeners() {
        // AI response
        this.socket.on('ai_response', (data) => {
            this.hideTypingIndicator();
            this.addMessage('assistant', data.message, data.dataDriven);
            this.enableInput();
        });

        // Content generation
        this.socket.on('content_generated', (data) => {
            this.hideTypingIndicator();
            this.addMessage('assistant', `Generated ${data.contentType}:\n\n${data.content}`);
            this.enableInput();
        });

        // Website analysis
        this.socket.on('analysis_started', (data) => {
            this.showTypingIndicator('Analyzing website...');
        });

        this.socket.on('analysis_complete', (data) => {
            this.hideTypingIndicator();
            if (data.success) {
                this.addMessage('assistant', this.formatAnalysisResults(data.analysis, data.recommendations));
            } else {
                this.addMessage('assistant', `Analysis failed: ${data.error}`);
            }
            this.enableInput();
        });

        // Chat history
        this.socket.on('chat_history', (data) => {
            this.loadChatHistory(data.history);
        });

        // History cleared
        this.socket.on('history_cleared', (data) => {
            this.addMessage('assistant', 'Conversation history cleared. How can I help you?');
        });
    }

    sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message) return;

        this.addMessage('user', message);
        this.messageInput.value = '';
        this.disableInput();
        this.showTypingIndicator();

        // Get website URL if provided
        const websiteUrl = this.websiteUrlInput.value.trim();

        // Send message to server
        this.socket.emit('chat_message', {
            message: message,
            userId: this.userId,
            websiteUrl: websiteUrl
        });
    }

    analyzeWebsite() {
        const url = this.websiteInput.value.trim();
        if (!url) {
            this.addMessage('assistant', 'Please enter a website URL to analyze.');
            return;
        }

        this.disableInput();
        this.showTypingIndicator('Analyzing website...');

        this.socket.emit('analyze_website', {
            url: url,
            userId: this.userId
        });
    }

    analyzeWebsiteUrl() {
        const url = this.websiteUrlInput.value.trim();
        if (!url) {
            this.addMessage('assistant', 'Please enter a website URL to get personalized recommendations.');
            return;
        }

        // Store the URL for future chat messages
        this.currentWebsiteUrl = url;
        
        this.addMessage('assistant', `✅ Website URL set: ${url}\n\nNow I can provide personalized SEO recommendations based on your website data. Try asking me about:\n\n• "What keywords should I target?"\n• "How can I improve my content?"\n• "What technical SEO issues do I have?"\n• "Who are my competitors?"`);
    }

    handleQuickAction(action) {
        const messages = {
            keywords: "Help me with keyword research for my website. What keywords should I target and how do I find them?",
            content: "I need help optimizing my website content for SEO. Can you analyze my content and provide recommendations?",
            technical: "What technical SEO issues should I focus on to improve my website's performance?",
            meta: "Help me optimize my meta tags, titles, and descriptions for better SEO performance."
        };

        const message = messages[action];
        if (message) {
            this.messageInput.value = message;
            this.sendMessage();
        }
    }

    clearHistory() {
        this.socket.emit('clear_history', {
            userId: this.userId
        });
    }

    addMessage(sender, content, dataDriven = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}`;
        
        const avatar = document.createElement('div');
        avatar.className = 'message-avatar';
        avatar.innerHTML = sender === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        
        // Add data-driven badge if applicable
        let contentHtml = this.formatMessage(content);
        if (dataDriven && sender === 'assistant') {
            contentHtml += '<span class="data-driven-badge">📊 Data-Driven</span>';
        }
        
        messageContent.innerHTML = contentHtml;
        
        messageDiv.appendChild(avatar);
        messageDiv.appendChild(messageContent);
        
        this.chatMessages.appendChild(messageDiv);
        this.scrollToBottom();
    }

    formatMessage(content) {
        // Convert line breaks to HTML
        return content.replace(/\n/g, '<br>');
    }

    formatAnalysisResults(analysis, recommendations) {
        let result = `📊 **Website Analysis Results**\n\n`;
        
        result += `**Basic Info:**\n`;
        result += `• Title: ${analysis.title || 'Not found'}\n`;
        result += `• Meta Description: ${analysis.metaDescription || 'Not found'}\n`;
        result += `• SEO Score: ${analysis.score || 'N/A'}/100\n\n`;
        
        result += `**Performance:**\n`;
        result += `• Load Time: ${analysis.performance?.loadTime || 'N/A'}\n`;
        result += `• Page Size: ${analysis.performance?.pageSize || 'N/A'} KB\n\n`;
        
        result += `**Content:**\n`;
        result += `• Word Count: ${analysis.content?.wordCount || 'N/A'}\n`;
        result += `• Images: ${analysis.images?.total || 0} total, ${analysis.images?.missingAlt || 0} missing alt text\n`;
        result += `• Links: ${analysis.links?.internal || 0} internal, ${analysis.links?.external || 0} external\n\n`;
        
        if (recommendations && recommendations.length > 0) {
            result += `**Recommendations:**\n`;
            recommendations.forEach((rec, index) => {
                result += `${index + 1}. ${rec}\n`;
            });
        }
        
        return result;
    }

    showTypingIndicator(message = 'AI is typing...') {
        this.typingIndicator.style.display = 'flex';
        this.typingIndicator.querySelector('.message-content span').textContent = message;
    }

    hideTypingIndicator() {
        this.typingIndicator.style.display = 'none';
    }

    disableInput() {
        this.sendButton.disabled = true;
        this.messageInput.disabled = true;
        this.analyzeButton.disabled = true;
        this.chatForm.classList.add('loading');
    }

    enableInput() {
        this.sendButton.disabled = false;
        this.messageInput.disabled = false;
        this.analyzeButton.disabled = false;
        this.chatForm.classList.remove('loading');
        this.messageInput.focus();
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    loadChatHistory(history) {
        // Clear current messages except the welcome message
        const welcomeMessage = this.chatMessages.querySelector('.message');
        this.chatMessages.innerHTML = '';
        if (welcomeMessage) {
            this.chatMessages.appendChild(welcomeMessage);
        }

        // Load history messages
        history.forEach(msg => {
            if (msg.role === 'user' || msg.role === 'assistant') {
                this.addMessage(msg.role, msg.content);
            }
        });
    }
}

// Initialize chat interface when page loads
document.addEventListener('DOMContentLoaded', () => {
    new AIChatInterface();
});
