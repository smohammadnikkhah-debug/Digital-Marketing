// WebSocket server for real-time AI chat
const { Server } = require('socket.io');
const aiChatService = require('./aiChatService');
const boostrampService = require('./boostrampService');
const dataforseoService = require('./dataforseoService');
const seoResponseService = require('./seoResponseService');
const contentSuggestionService = require('./contentSuggestionService');
const subpageAnalysisService = require('./subpageAnalysisService');

class ChatServer {
  constructor(httpServer) {
    this.io = new Server(httpServer, {
      cors: {
        origin: "*",
        methods: ["GET", "POST"]
      }
    });
    
    this.setupEventHandlers();
  }

  setupEventHandlers() {
    this.io.on('connection', (socket) => {
      console.log('🔌 User connected:', socket.id);

      // Handle chat messages
      socket.on('chat_message', async (data) => {
        try {
          const { message, userId, websiteUrl } = data;
          
          // If website URL is provided, get data for context
          let websiteData = null;
          if (websiteUrl) {
            try {
              // Process URL - add https:// if missing
              let processedUrl = websiteUrl.trim();
              if (!processedUrl.match(/^https?:\/\//)) {
                processedUrl = 'https://' + processedUrl;
              }
              
              // Try DataForSEO first (which will return demo data if not configured)
              const dataforseoService = require('./dataforseoService');
              const analysis = await dataforseoService.analyzeWebsite(processedUrl);
              if (analysis.success) {
                websiteData = analysis.analysis;
                console.log('✅ Got website data for AI context');
              }
            } catch (error) {
              console.log('Website analysis failed, proceeding without data:', error.message);
            }
          }

          // Try OpenAI first, then fall back to intelligent recommendations
          let response = await aiChatService.processMessage(userId, message, websiteData);
          
          // If OpenAI failed, try intelligent recommendations
          if (!response || !response.success) {
            console.log('OpenAI failed, trying intelligent recommendations...');
            response = await aiChatService.generateIntelligentRecommendations(userId, message, websiteUrl);
          }
          
          // Send response back to client
          socket.emit('ai_response', {
            message: response.message,
            success: response.success,
            timestamp: response.timestamp,
            dataDriven: response.dataDriven || false
          });

        } catch (error) {
          console.error('Chat message error:', error);
          socket.emit('ai_response', {
            message: 'Sorry, I encountered an error. Please try again.',
            success: false,
            timestamp: new Date().toISOString()
          });
        }
      });

      // Handle content generation requests
      socket.on('generate_content', async (data) => {
        try {
          const { contentType, websiteData, userId } = data;
          
          const response = await aiChatService.generateSEOContent(
            userId, 
            contentType, 
            websiteData
          );
          
          socket.emit('content_generated', {
            content: response.content,
            success: response.success,
            contentType: contentType,
            timestamp: response.timestamp
          });

        } catch (error) {
          console.error('Content generation error:', error);
          socket.emit('content_generated', {
            content: 'Sorry, I could not generate content at this time.',
            success: false,
            contentType: data.contentType,
            timestamp: new Date().toISOString()
          });
        }
      });

      // Handle website analysis requests (DataForSEO)
      socket.on('analyze_website', async (data) => {
        try {
          const { url } = data;
          
          // Process URL - add https:// if missing
          let processedUrl = url.trim();
          if (!processedUrl.match(/^https?:\/\//)) {
            processedUrl = 'https://' + processedUrl;
          }
          
          socket.emit('analysis_started', {
            message: 'Starting comprehensive website analysis...',
            url: processedUrl
          });

          // Step 1: Discover all subpages
          socket.emit('analysis_progress', {
            message: 'Discovering all pages and subpages...',
            progress: 10
          });
          
          const discoveredPages = await subpageAnalysisService.discoverSubpages(processedUrl);
          
          socket.emit('analysis_progress', {
            message: `Found ${discoveredPages.length} pages. Analyzing each page...`,
            progress: 30
          });

          // Step 2: Analyze all discovered pages
          const pageAnalyses = await subpageAnalysisService.analyzeAllPages(discoveredPages, boostrampService);
          
          socket.emit('analysis_progress', {
            message: 'Generating comprehensive website report...',
            progress: 80
          });

          // Step 3: Generate comprehensive website report
          const websiteReport = subpageAnalysisService.generateWebsiteReport(pageAnalyses);
          
          if (websiteReport.success) {
            socket.emit('analysis_complete', {
              success: true,
              analysis: websiteReport.analysis,
              recommendations: websiteReport.analysis.recommendations,
              timestamp: websiteReport.timestamp
            });
          } else {
            // Fallback to single page analysis
            console.log('Subpage analysis failed, falling back to single page analysis');
            
            // Try DataForSEO first, fallback to Boostramp
            let analysisResult;
            try {
              analysisResult = await dataforseoService.analyzeWebsite(processedUrl);
              if (analysisResult.success) {
                socket.emit('analysis_complete', {
                  success: true,
                  analysis: analysisResult.analysis,
                  recommendations: analysisResult.analysis.recommendations,
                  timestamp: analysisResult.timestamp
                });
                return;
              }
            } catch (dataforseoError) {
              console.log('DataForSEO analysis failed, falling back to Boostramp:', dataforseoError.message);
            }

            // Fallback to Boostramp
            const analysis = await boostrampService.scrapeWebsite(processedUrl);
            const recommendations = boostrampService.generateRecommendations(analysis, null);
            const score = boostrampService.calculateSEOScore(analysis, null);

            socket.emit('analysis_complete', {
              success: true,
              analysis: {
                ...analysis,
                score: score
              },
              recommendations: recommendations,
              timestamp: new Date().toISOString()
            });
          }

        } catch (error) {
          console.error('Website analysis error:', error);
          socket.emit('analysis_complete', {
            success: false,
            error: error.message || 'Analysis failed',
            timestamp: new Date().toISOString()
          });
        }
      });

      // Handle conversation history requests
      socket.on('get_history', (data) => {
        const { userId } = data;
        const history = aiChatService.getHistory(userId);
        
        socket.emit('chat_history', {
          history: history,
          userId: userId
        });
      });

      // Handle conversation clear
      socket.on('clear_history', (data) => {
        const { userId } = data;
        aiChatService.clearHistory(userId);
        
        socket.emit('history_cleared', {
          userId: userId,
          message: 'Conversation history cleared'
        });
      });

      // Handle customer SEO requests with Boostramp integration
      socket.on('seo_request', async (data) => {
        try {
          const { request, websiteUrl, userId = 'anonymous' } = data;
          
          console.log(`🔍 Processing SEO request: "${request}" for website: ${websiteUrl || 'N/A'}`);
          
          // Process URL - add https:// if missing
          let processedUrl = websiteUrl;
          if (processedUrl && !processedUrl.match(/^https?:\/\//)) {
            processedUrl = 'https://' + processedUrl;
          }

          // Send processing status
          socket.emit('seo_processing', {
            message: 'Analyzing your request and website data...',
            status: 'processing'
          });

          // Process request with Boostramp integration
          const response = await seoResponseService.processCustomerRequest(userId, request, processedUrl);
          
          socket.emit('seo_response', {
            success: response.success,
            response: response.response,
            websiteData: response.websiteData,
            timestamp: response.timestamp
          });
          
        } catch (error) {
          console.error('SEO request error:', error);
          socket.emit('seo_response', {
            success: false,
            response: 'Sorry, I encountered an error processing your SEO request. Please try again.',
            timestamp: new Date().toISOString()
          });
        }
      });

      // Handle content suggestions requests
      socket.on('get_content_suggestions', async (data) => {
        try {
          const { websiteAnalysis } = data;
          
          console.log('💡 Generating AI-powered content suggestions...');
          
          // Send processing status
          socket.emit('suggestions_processing', {
            message: 'Generating AI-powered content suggestions...',
            status: 'processing'
          });

          // Generate content suggestions
          const suggestions = await contentSuggestionService.generateContentSuggestions(websiteAnalysis);
          
          socket.emit('content_suggestions', {
            success: suggestions.success,
            suggestions: suggestions.suggestions,
            timestamp: suggestions.timestamp
          });
          
        } catch (error) {
          console.error('Content suggestions error:', error);
          socket.emit('content_suggestions', {
            success: false,
            suggestions: null,
            error: 'Failed to generate content suggestions',
            timestamp: new Date().toISOString()
          });
        }
      });

      // Handle disconnection
      socket.on('disconnect', () => {
        console.log('🔌 User disconnected:', socket.id);
      });
    });
  }

  // Broadcast message to all connected clients
  broadcast(message, data) {
    this.io.emit(message, data);
  }

  // Send message to specific user
  sendToUser(userId, message, data) {
    this.io.to(userId).emit(message, data);
  }
}

module.exports = ChatServer;
