'use client';

import DOMPurify from 'dompurify';
import type { HTMLAttributes } from 'react';

/**
 * Rendering the rich text this platform stores, without trusting it.
 *
 * Job descriptions, training-programme descriptions and announcements are
 * written by companies, administrators and a JobStreet scraper. The backend
 * sanitizes them on the way in, so the database should never hold anything
 * executable — but "should" is not a security boundary. This is the second,
 * independent pass, and the reason it exists:
 *
 *   • rows written before the backend sanitizer existed;
 *   • any future write path that bypasses the model layer;
 *   • an API response that did not come from our own database at all.
 *
 * The stakes are specific: this application keeps its JWT in localStorage, so
 * script running on the page can read the token and take the account. One
 * missed escape is a full account takeover, not a cosmetic bug.
 *
 * The allowlist mirrors `backend/config/sanitization.py`. Keep them in step —
 * a tag allowed on one side and stripped on the other is a rendering bug, and
 * a tag allowed here but not there is a hole.
 */

/** Tags a description or announcement legitimately uses. */
const ALLOWED_TAGS = [
  'p', 'br', 'hr', 'div', 'span',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'strong', 'b', 'em', 'i', 'u', 's', 'sub', 'sup', 'small', 'mark',
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  'blockquote', 'pre', 'code',
  'a',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
];

/**
 * No `style`: it carries its own injection surface, and the platform's CSS
 * controls presentation. No `on*` — DOMPurify strips every event handler by
 * default, and the explicit allowlist below means one could not be added back
 * by accident.
 */
const ALLOWED_ATTR = [
  'href', 'title', 'target', 'rel',
  'colspan', 'rowspan', 'scope', 'start',
  'class',
];

/**
 * Sanitize a stored HTML string down to the allowlist.
 *
 * Returns '' for null/undefined so a caller can render the result
 * unconditionally.
 */
export function sanitizeHtml(html: string | null | undefined): string {
  if (!html) return '';
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    // Belt and braces: these are absent from ALLOWED_TAGS already, but naming
    // them means a careless addition to that list cannot re-admit them.
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form',
                  'input', 'button', 'svg', 'math', 'noscript', 'base'],
    FORBID_ATTR: ['style', 'srcset', 'formaction', 'xlink:href'],
    // Blocks javascript: and data: URLs on href/target.
    ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.-]+(?:[^a-z+.\-:]|$))/i,
    // Reject `<html>`/`<body>` wrappers rather than letting content escape
    // the fragment it is supposed to be.
    WHOLE_DOCUMENT: false,
    RETURN_DOM: false,
    RETURN_DOM_FRAGMENT: false,
  });
}

type RichTextProps = HTMLAttributes<HTMLDivElement> & {
  html: string | null | undefined;
};

/**
 * The only component that may render stored HTML.
 *
 * `dangerouslySetInnerHTML` appears here and nowhere else in the app, so
 * "is this string sanitized?" has exactly one answer to check rather than ten
 * call sites to audit.
 */
export function RichText({ html, ...props }: RichTextProps) {
  return <div {...props} dangerouslySetInnerHTML={{ __html: sanitizeHtml(html) }} />;
}
