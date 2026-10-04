/**
 * ==============================================================================
 * Mozarex Automated Website Review — PDF Report Generation Service
 * ==============================================================================
 * Generates professionally branded, publication-ready PDF audits for prospects.
 * Follows the Mozarex Design System (Deep Navy, Mozarex Blue, Generous Whitespace,
 * Restrained Structured Finding Cards).
 */

const PDFDocument = require('pdfkit');
const path = require('path');
const fs = require('fs');

// Mozarex Color Palette Constants
const COLORS = {
  NAVY_PRIMARY: '#0B132B',
  NAVY_DARK: '#0F172A',
  NAVY_MUTED: '#334155',
  SLATE_BODY: '#475569',
  SLATE_LIGHT: '#64748B',
  SLATE_BORDER: '#E2E8F0',
  BG_CARD: '#F8FAFC',
  MOZAREX_BLUE: '#0066FF',
  MOZAREX_BLUE_DARK: '#0052CC',
  MOZAREX_BLUE_LIGHT: '#EFF6FF',
  WHITE: '#FFFFFF',
  ACCENT_GREEN: '#059669',
  ACCENT_GREEN_BG: '#ECFDF5'
};

/**
 * Sanitizes untrusted text by removing executable tags, non-printable characters,
 * and normalizing whitespace.
 * 
 * @param {string} text 
 * @returns {string}
 */
function sanitizeText(text) {
  if (typeof text !== 'string') return '';
  return text
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/<[^>]+>/g, '') // strip any HTML tags
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, '') // strip control chars
    .trim();
}

/**
 * Sanitizes business name for safe file naming (e.g. Mozarex-Website-Review-Frank-Bertone-Plumbing.pdf)
 * 
 * @param {string} businessName 
 * @returns {string}
 */
function sanitizeFileNamePart(businessName) {
  if (!businessName) return 'Business';
  return businessName
    .replace(/[^a-zA-Z0-9_-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || 'Business';
}

/**
 * Generates a branded Mozarex Website Review PDF Buffer.
 * 
 * @param {Object} auditData
 * @param {string} auditData.business_name
 * @param {string} [auditData.business_type]
 * @param {string} [auditData.suburb]
 * @param {string} auditData.website_url
 * @param {Array<Object>} auditData.findings
 * @param {number} [auditData.proposed_price]
 * @param {string} [auditData.currency]
 * @param {string} [auditData.public_token]
 * @param {string} [auditData.audit_id]
 * @returns {Promise<Buffer>}
 */
function generateAuditPdf(auditData) {
  return new Promise((resolve, reject) => {
    try {
      const doc = new PDFDocument({
        size: 'A4',
        margin: 50,
        bufferPages: true,
        info: {
          Title: `Mozarex Website Review - ${sanitizeText(auditData.business_name)}`,
          Author: 'Mozarex Digital Agency',
          Subject: 'Website Audit & Performance Review',
          Keywords: 'Mozarex, Website Review, Digital Strategy, Web Design',
          Creator: 'Mozarex Report Engine v1.0'
        }
      });

      const chunks = [];
      doc.on('data', chunk => chunks.push(chunk));
      doc.on('end', () => resolve(Buffer.concat(chunks)));
      doc.on('error', err => reject(err));

      const businessName = sanitizeText(auditData.business_name) || 'Valued Business';
      const businessType = sanitizeText(auditData.business_type);
      const suburb = sanitizeText(auditData.suburb);
      const websiteUrl = sanitizeText(auditData.website_url);
      const proposedPrice = auditData.proposed_price ? Number(auditData.proposed_price) : null;
      const currency = sanitizeText(auditData.currency) || 'AUD';
      const findings = Array.isArray(auditData.findings) ? auditData.findings : [];

      const pageWidth = doc.page.width;
      const contentWidth = pageWidth - 100; // 50 margin each side

      // ======================================================================
      // 1. BRAND HEADER & ACCENT BAR
      // ======================================================================
      
      // Mozarex Top Accent Strip
      doc.rect(0, 0, pageWidth, 6).fill(COLORS.MOZAREX_BLUE);

      // Logo or Mozarex Brand Wordmark
      const logoPath = path.join(__dirname, '..', 'images', 'Logo_M.png');
      if (fs.existsSync(logoPath)) {
        try {
          doc.image(logoPath, 50, 30, { width: 32, height: 32 });
          doc.fillColor(COLORS.NAVY_PRIMARY)
             .fontSize(20)
             .font('Helvetica-Bold')
             .text('MOZAREX', 90, 37);
        } catch (e) {
          doc.fillColor(COLORS.NAVY_PRIMARY)
             .fontSize(22)
             .font('Helvetica-Bold')
             .text('MOZAREX', 50, 35);
        }
      } else {
        doc.fillColor(COLORS.NAVY_PRIMARY)
           .fontSize(22)
           .font('Helvetica-Bold')
           .text('MOZAREX', 50, 35);
      }

      // Review Badge on Header Right
      doc.rect(pageWidth - 210, 32, 160, 24)
         .fillColor(COLORS.MOZAREX_BLUE_LIGHT)
         .fill();
      doc.rect(pageWidth - 210, 32, 160, 24)
         .strokeColor(COLORS.MOZAREX_BLUE)
         .lineWidth(0.5)
         .stroke();
      doc.fillColor(COLORS.MOZAREX_BLUE_DARK)
         .fontSize(9)
         .font('Helvetica-Bold')
         .text('FREE WEBSITE REVIEW', pageWidth - 200, 39, { width: 140, align: 'center' });

      // Subtle Divider
      doc.moveTo(50, 75)
         .lineTo(pageWidth - 50, 75)
         .strokeColor(COLORS.SLATE_BORDER)
         .lineWidth(1)
         .stroke();

      // ======================================================================
      // 2. HERO / PREPARED FOR SECTION
      // ======================================================================
      doc.y = 95;

      // Hero Card Background
      const heroCardY = doc.y;
      doc.rect(50, heroCardY, contentWidth, 90)
         .fillColor(COLORS.BG_CARD)
         .fill();
      doc.rect(50, heroCardY, contentWidth, 90)
         .strokeColor(COLORS.SLATE_BORDER)
         .lineWidth(1)
         .stroke();

      // Left Accent Strip on Hero Card
      doc.rect(50, heroCardY, 4, 90)
         .fillColor(COLORS.MOZAREX_BLUE)
         .fill();

      // Prepared For Content
      doc.fillColor(COLORS.SLATE_LIGHT)
         .fontSize(9)
         .font('Helvetica-Bold')
         .text('PREPARED EXCLUSIVELY FOR', 70, heroCardY + 14);

      doc.fillColor(COLORS.NAVY_PRIMARY)
         .fontSize(16)
         .font('Helvetica-Bold')
         .text(businessName, 70, heroCardY + 28, { width: contentWidth - 40 });

      let metaLine = '';
      if (businessType && suburb) {
        metaLine = `${businessType}  •  ${suburb}`;
      } else if (businessType) {
        metaLine = businessType;
      } else if (suburb) {
        metaLine = suburb;
      }

      if (metaLine) {
        doc.fillColor(COLORS.NAVY_MUTED)
           .fontSize(10)
           .font('Helvetica')
           .text(metaLine, 70, heroCardY + 49);
      }

      doc.fillColor(COLORS.MOZAREX_BLUE)
         .fontSize(10)
         .font('Helvetica-Bold')
         .text(`Website: ${websiteUrl}`, 70, heroCardY + 66, {
           link: websiteUrl.startsWith('http') ? websiteUrl : `https://${websiteUrl}`
         });

      // ======================================================================
      // 3. INTRODUCTION
      // ======================================================================
      doc.y = heroCardY + 105;

      doc.fillColor(COLORS.SLATE_BODY)
         .fontSize(10.5)
         .font('Helvetica')
         .text(
           'We reviewed your website to identify practical opportunities to improve usability, customer enquiries, and your overall digital presence.',
           50,
           doc.y,
           { width: contentWidth, lineGap: 3 }
         );

      doc.moveDown(1.2);

      // ======================================================================
      // 4. KEY OPPORTUNITIES IDENTIFIED (FINDINGS)
      // ======================================================================
      doc.fillColor(COLORS.NAVY_PRIMARY)
         .fontSize(13)
         .font('Helvetica-Bold')
         .text('KEY OPPORTUNITIES IDENTIFIED', 50, doc.y);

      doc.moveDown(0.6);

      findings.forEach((finding, index) => {
        const findingNum = String(index + 1).padStart(2, '0');
        const title = sanitizeText(finding.title) || `Opportunity ${findingNum}`;
        const description = sanitizeText(finding.description) || '';
        const recommendation = sanitizeText(finding.recommendation) || '';
        const category = sanitizeText(finding.category);

        // Check if we need a new page for this finding
        if (doc.y > 660) {
          doc.addPage();
          doc.y = 50;
        }

        const startY = doc.y;

        // Finding Card Header
        doc.rect(50, startY, contentWidth, 24)
           .fillColor(COLORS.NAVY_PRIMARY)
           .fill();

        doc.fillColor(COLORS.WHITE)
           .fontSize(9)
           .font('Helvetica-Bold')
           .text(`FINDING ${findingNum}`, 62, startY + 7);

        if (category) {
          const formattedCat = category.replace(/_/g, ' ').toUpperCase();
          doc.fillColor(COLORS.SLATE_BORDER)
             .fontSize(8)
             .font('Helvetica')
             .text(formattedCat, pageWidth - 200, startY + 8, { width: 140, align: 'right' });
        }

        doc.y = startY + 34;

        // Finding Title
        doc.fillColor(COLORS.NAVY_PRIMARY)
           .fontSize(11.5)
           .font('Helvetica-Bold')
           .text(title, 60, doc.y, { width: contentWidth - 20 });

        doc.moveDown(0.4);

        // Description
        if (description) {
          doc.fillColor(COLORS.SLATE_BODY)
             .fontSize(9.5)
             .font('Helvetica')
             .text(description, 60, doc.y, { width: contentWidth - 20, lineGap: 2 });
          doc.moveDown(0.5);
        }

        // Recommendation Box
        if (recommendation) {
          const recBoxY = doc.y;
          doc.rect(60, recBoxY, contentWidth - 20, 1)
             .fillColor(COLORS.SLATE_BORDER)
             .fill();
          
          doc.y = recBoxY + 8;
          doc.fillColor(COLORS.MOZAREX_BLUE_DARK)
             .fontSize(9)
             .font('Helvetica-Bold')
             .text('RECOMMENDATION', 60, doc.y);

          doc.moveDown(0.3);
          doc.fillColor(COLORS.NAVY_PRIMARY)
             .fontSize(9.5)
             .font('Helvetica')
             .text(recommendation, 60, doc.y, { width: contentWidth - 20, lineGap: 2 });
          doc.moveDown(0.6);
        }

        // Draw card boundary
        const cardHeight = doc.y - startY;
        doc.rect(50, startY, contentWidth, cardHeight)
           .strokeColor(COLORS.SLATE_BORDER)
           .lineWidth(1)
           .stroke();

        doc.y += 14;
      });

      // ======================================================================
      // 5. RECOMMENDED WEBSITE APPROACH & COMMERCIALS
      // ======================================================================
      // Check space on page, else add page
      if (doc.y > 580) {
        doc.addPage();
        doc.y = 50;
      }

      const approachStartY = doc.y;
      doc.fillColor(COLORS.NAVY_PRIMARY)
         .fontSize(13)
         .font('Helvetica-Bold')
         .text('RECOMMENDED WEBSITE APPROACH', 50, approachStartY);

      doc.moveDown(0.5);

      if (proposedPrice && proposedPrice > 0) {
        const pricingCardY = doc.y;
        
        doc.rect(50, pricingCardY, contentWidth, 54)
           .fillColor(COLORS.ACCENT_GREEN_BG)
           .fill();
        doc.rect(50, pricingCardY, contentWidth, 54)
           .strokeColor(COLORS.ACCENT_GREEN)
           .lineWidth(1)
           .stroke();

        doc.fillColor(COLORS.NAVY_PRIMARY)
           .fontSize(10)
           .font('Helvetica-Bold')
           .text('ESTIMATED PROJECT INVESTMENT', 65, pricingCardY + 12);

        const formattedPrice = `$${proposedPrice.toLocaleString('en-AU')}`;
        doc.fillColor(COLORS.ACCENT_GREEN)
           .fontSize(16)
           .font('Helvetica-Bold')
           .text(formattedPrice, 65, pricingCardY + 26);

        doc.fillColor(COLORS.SLATE_BODY)
           .fontSize(9.5)
           .font('Helvetica')
           .text('Fixed price for agreed project scope.', 185, pricingCardY + 30);

        doc.y = pricingCardY + 66;
      }

      // Required Standard Pricing Disclaimer
      doc.fillColor(COLORS.SLATE_LIGHT)
         .fontSize(8)
         .font('Helvetica')
         .text(
           'Pricing is based on the website requirements identified during our initial review and the agreed project scope. Final pricing may vary depending on page count, functionality, e-commerce, integrations, content, imagery, video and other requirements. Your final fixed price will be confirmed before development begins.',
           50,
           doc.y,
           { width: contentWidth, lineGap: 1.5 }
         );

      // ======================================================================
      // 6. GLOBAL FOOTER ON ALL PAGES
      // ======================================================================
      const range = doc.bufferedPageRange();
      for (let i = range.start; i < range.start + range.count; i++) {
        doc.switchToPage(i);

        // Footer divider line
        doc.moveTo(50, doc.page.height - 45)
           .lineTo(pageWidth - 50, doc.page.height - 45)
           .strokeColor(COLORS.SLATE_BORDER)
           .lineWidth(0.5)
           .stroke();

        // Footer Brand & Location
        doc.fillColor(COLORS.NAVY_MUTED)
           .fontSize(8.5)
           .font('Helvetica-Bold')
           .text('Mozarex Digital Agency', 50, doc.page.height - 35);

        doc.fillColor(COLORS.SLATE_LIGHT)
           .fontSize(8)
           .font('Helvetica')
           .text('  •  Melbourne, Australia  •  ', 145, doc.page.height - 35);

        doc.fillColor(COLORS.MOZAREX_BLUE)
           .fontSize(8)
           .font('Helvetica-Bold')
           .text('mozarex.com', 255, doc.page.height - 35, { link: 'https://mozarex.com' });

        // Page Number
        doc.fillColor(COLORS.SLATE_LIGHT)
           .fontSize(8)
           .font('Helvetica')
           .text(`Page ${i + 1} of ${range.count}`, pageWidth - 120, doc.page.height - 35, {
             width: 70,
             align: 'right'
           });
      }

      doc.end();
    } catch (error) {
      reject(error);
    }
  });
}

module.exports = {
  generateAuditPdf,
  sanitizeText,
  sanitizeFileNamePart
};
