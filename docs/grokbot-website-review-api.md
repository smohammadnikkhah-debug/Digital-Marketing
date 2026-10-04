# Mozarex Website Review API Specification (Grokbot Integration) — Phase 1

## Overview
The Mozarex Website Review API allows Grokbot to submit structured prospect website audits. Upon receiving an audit, Mozarex automatically validates input, checks for duplicate prospect domains, creates a database record in `public.website_audits`, generates a cryptographically secure token, renders a branded Mozarex PDF report, and stores the PDF in private Supabase Storage (`mozarex-website-reviews`).

> **Note on Email Policy**: Creating a report **NEVER** sends an email or marks an audit as approved. Email outreach is a separate, human-reviewed workflow.

---

## 1. Authentication

All requests to the Grokbot creation endpoint require a dedicated Bearer token in the `Authorization` header:

```http
Authorization: Bearer <MOZAREX_GROKBOT_API_KEY>
```

- Failed authentication returns `401 Unauthorized` with error code `INVALID_AUTH`.
- Constant-time comparison is enforced on the server to prevent timing attacks.
- Do not commit or expose this key in public repositories or frontend code.

---

## 2. Create Website Review Endpoint

### `POST /create-website-review`
*(Also accessible at `POST /api/website-review/create`)*

### Headers
```http
Content-Type: application/json
Authorization: Bearer <MOZAREX_GROKBOT_API_KEY>
```

### Request Schema

| Field | Type | Required | Description | Constraints |
| :--- | :--- | :--- | :--- | :--- |
| `business_name` | `string` | **Yes** | Trading or business name of the prospect | Max 200 chars, non-empty |
| `business_type` | `string` | No | Industry category (e.g. "Plumbing", "Dental") | Max 100 chars |
| `suburb` | `string` | No | Location / suburb (e.g. "Melbourne", "Hoppers Crossing") | Max 100 chars |
| `website_url` | `string` | **Yes** | Prospect's current website URL | Valid http/https URL, max 500 chars |
| `contact_email` | `string` | No | Discovered contact email for the business | Valid email format if provided, max 255 chars |
| `findings` | `array[object]` | **Yes** | Array of structured audit findings | 1 to 20 items |
| `proposed_price` | `number` | No | Estimated fixed project investment amount in AUD | Positive number (> 0). Do not invent if unknown |
| `currency` | `string` | No | Currency code (default `'AUD'`) | Currently only `'AUD'` is accepted |

#### Finding Item Schema

| Field | Type | Required | Description | Constraints |
| :--- | :--- | :--- | :--- | :--- |
| `title` | `string` | **Yes** | Short headline of the opportunity | Max 200 chars |
| `description` | `string` | **Yes** | Detailed observation / issue found | Max 2000 chars |
| `recommendation` | `string` | **Yes** | Practical, actionable solution | Max 2000 chars |
| `category` | `string` | No | Category tag (e.g. `conversion`, `lead_generation`, `seo`, `speed`) | Max 100 chars |
| `screenshot_path` | `string` | No | Optional reference path | String or null |

---

### Example Request

```json
{
  "business_name": "Frank Bertone Plumbing",
  "business_type": "Plumbing",
  "suburb": "Hoppers Crossing",
  "website_url": "https://frankbertoneplumbing.com.au",
  "contact_email": "info@frankbertoneplumbing.com.au",
  "findings": [
    {
      "title": "Mobile Calling & Click-to-Call",
      "description": "The primary telephone number on the header and mobile viewport is formatted as plain text rather than an active tap-to-call link.",
      "recommendation": "Convert all visible phone numbers into tel: links with prominent sticky mobile call buttons to increase emergency lead capture.",
      "category": "conversion"
    },
    {
      "title": "Quote Enquiry Capture",
      "description": "No dedicated short quote request form was found on high-intent service landing pages.",
      "recommendation": "Deploy a high-converting 3-step quote form directly below the primary hero section.",
      "category": "lead_generation"
    }
  ],
  "proposed_price": 1490,
  "currency": "AUD"
}
```

---

### Example Success Response (`201 Created`)

```json
{
  "success": true,
  "audit_id": "7b68a804-9c87-43cf-bc0a-4712ce3c4be1",
  "status": "ready",
  "business_name": "Frank Bertone Plumbing",
  "report_url": "https://mozarex.com/review/7x91kLmNpQ2vW8zR4tY5aBcDe",
  "download_url": "https://mozarex.com/review/7x91kLmNpQ2vW8zR4tY5aBcDe/download"
}
```

---

## 3. Duplicate Prevention Behavior

To prevent accidental duplicate outreach or multi-audit generation for the same prospect, all submitted URLs are normalized to their canonical domain:

- `https://www.example.com/about` $\rightarrow$ `example.com`
- `http://example.com/` $\rightarrow$ `example.com`

If an active audit already exists for the domain, the API will **NOT** overwrite the existing audit. It returns HTTP `409 Conflict`:

```json
{
  "success": false,
  "code": "AUDIT_ALREADY_EXISTS",
  "message": "An active website audit already exists for this domain.",
  "existing_audit_id": "7b68a804-9c87-43cf-bc0a-4712ce3c4be1",
  "existing_report_url": "https://mozarex.com/review/7x91kLmNpQ2vW8zR4tY5aBcDe"
}
```

---

## 4. Rate Limiting

- Limit: **200 requests per hour** per API client (configurable via `GROKBOT_RATE_LIMIT_PER_HOUR`).
- Exceeding the threshold returns HTTP `429 Too Many Requests`:

```json
{
  "success": false,
  "code": "RATE_LIMITED",
  "error": "Too many audit submission requests. Please try again later."
}
```

---

## 5. Error Code Reference

| HTTP Status | Error Code | Description |
| :--- | :--- | :--- |
| `400 Bad Request` | `INVALID_INPUT` | Missing or invalid request fields (e.g. invalid URL, empty findings, negative price). |
| `401 Unauthorized` | `INVALID_AUTH` | Missing, incorrect, or malformed `Authorization: Bearer <key>` header. |
| `409 Conflict` | `AUDIT_ALREADY_EXISTS` | An active audit already exists for this website domain. |
| `429 Too Many Requests` | `RATE_LIMITED` | Submission rate limit exceeded. |
| `500 Internal Error` | `PDF_GENERATION_FAILED` | Internal error generating the branded PDF document. |
| `502 Bad Gateway` | `STORAGE_UPLOAD_FAILED` | Error storing the PDF in private Supabase Storage. |
| `500 Internal Error` | `DATABASE_ERROR` | Database insertion or update error. |

---

## 6. Public Report & Download Endpoints

### Report Download: `GET /review/:token/download`
- Validates the 256-bit cryptographically secure token.
- Automatically increments `download_count` and updates `first_downloaded_at` / `last_downloaded_at`.
- Securely streams the PDF with:
  - `Content-Type: application/pdf`
  - `Content-Disposition: attachment; filename="Mozarex-Website-Review-{Business-Name}.pdf"`

### Report Public Data (DTO): `GET /review/:token/data`
- Returns strictly allowlisted public report fields for web rendering without exposing prospect contact information or database internals:

```json
{
  "success": true,
  "business_name": "Frank Bertone Plumbing",
  "business_type": "Plumbing",
  "suburb": "Hoppers Crossing",
  "website_url": "https://frankbertoneplumbing.com.au",
  "findings": [ ... ],
  "proposed_price": 1490,
  "currency": "AUD",
  "report_available": true,
  "report_url": "https://mozarex.com/review/7x91kLmNpQ2vW8zR4tY5aBcDe",
  "download_url": "https://mozarex.com/review/7x91kLmNpQ2vW8zR4tY5aBcDe/download"
}
```
*(All operational metrics, database UUIDs, storage paths, emails, and workflow timestamps are strictly excluded)*

